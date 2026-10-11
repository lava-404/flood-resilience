"""Forecast worker: consumes a job, runs the engine, persists. Idempotent by job_key (SRS FR-17)."""
from .engine import run_forecast


def handle_job(job, repo, now, model_version=None):
    key = job["job_key"]
    if repo.has_job(key):
        return "duplicate"
    st = repo.get_station(job["station_id"])
    if st is None:
        raise LookupError(f"unknown station {job['station_id']}")
    levels = [(o.observed_at, o.value) for o in repo.observations(st.id, "river_level", now) if o.value is not None]
    rain = [(o.observed_at, o.value) for o in repo.observations(st.id, "rainfall", now) if o.value is not None]
    offs = repo.observations(st.id, "official_status", now)
    official = ({"status": offs[-1].text_value, "observed_at": offs[-1].observed_at, "source": offs[-1].source}
                if offs else None)
    kw = {"model_version": model_version} if model_version else {}
    result = run_forecast(levels, rain, official, {"warning": st.threshold_warning, "danger": st.threshold_danger},
                          now, location_id=st.id, **kw)
    result["run_id"], result["job_key"], result["data_provenance"] = job.get("run_id"), key, st.provenance
    repo.save_risk(st.id, result, key)
    return "ok"
