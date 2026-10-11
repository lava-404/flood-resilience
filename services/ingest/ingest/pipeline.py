"""Ingestion run: fetch -> raw snapshot -> normalize -> quality flags -> upsert -> run record -> forecast job.
A run is only 'success' if every step including the snapshot write succeeded (SRS 15)."""
import uuid
from collections import defaultdict
from floodres import quality
from .adapters import SourceUnavailable


def run_ingestion(adapter, repo, snapshots, queue, now, run_id=None, as_of=None):
    run = {"run_id": run_id or str(uuid.uuid4()), "source": adapter.name, "started_at": now,
           "finished_at": None, "status": "running", "records": 0, "last_observed_at": None, "error": None}
    try:
        raw = adapter.fetch(now)
        run["snapshot_key"] = snapshots.put(adapter.name, raw)
        stations, obs = adapter.normalize(raw, now)
        obs = _flag_levels(obs)
        for s in stations: repo.upsert_station(s)           # stations first: observations FK -> stations
        repo.upsert_observations(obs)
        run["records"] = len(obs)
        run["last_observed_at"] = max((o.observed_at for o in obs), default=None)
        run["status"] = "success"
        for s in stations:
            # Key on the newest input of ANY parameter: an official-warning or rainfall update must trigger a new
            # forecast even when the river gauge is silent (otherwise an official warning could go unreflected).
            cut = max((o.observed_at for o in obs if o.station_id == s.id), default=None)
            if cut:
                queue.publish({"job_key": f"{s.id}:{cut.isoformat()}", "station_id": s.id, "data_cutoff": cut.isoformat(),
                               "run_id": run["run_id"], "as_of": (as_of or now).isoformat()})
    except SourceUnavailable as e:
        run.update(status="source_unavailable", error=str(e))
    except Exception as e:                                   # never report success on partial failure
        run.update(status="failed", error=f"{type(e).__name__}: {e}")
    finally:
        run["finished_at"] = now
        repo.record_run(run)
    return run


def _flag_levels(obs):
    """Keep every record (FR-06 provenance) but mark implausible river levels so they are visible."""
    by = defaultdict(list)
    for o in obs:
        if o.parameter == "river_level": by[o.station_id].append(o)
    bad = {}
    for sid, rows in by.items():
        rows.sort(key=lambda o: o.observed_at)
        _, flags = quality.screen_levels([(o.observed_at, o.value) for o in rows])
        bad.update({(sid, f["observed_at"]): f["reason"] for f in flags})
    return [o.__class__(**{**o.__dict__, "quality_flag": bad[(o.station_id, o.observed_at)]})
            if o.parameter == "river_level" and (o.station_id, o.observed_at) in bad else o for o in obs]
