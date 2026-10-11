"""Deterministic historical-event replay (FR-14). Steps the engine hour by hour over a fixture."""
import json
from datetime import datetime, timedelta
from .engine import run_forecast


def _p(s): return datetime.fromisoformat(s)


def load(path):
    with open(path) as f: d = json.load(f)
    d["levels"] = [(_p(r["t"]), r["value"]) for r in d["levels"]]
    d["rain"] = [(_p(r["t"]), r["value"]) for r in d["rain"]]
    d["official"] = [(_p(r["t"]), r["status"]) for r in d["official"]]
    return d


def replay(fx, step_hours=1):
    """Yields one forecast per step. Official status is the latest record <= now. Labels synthetic data."""
    start, end = fx["levels"][0][0], fx["rain"][-1][0]
    now = start + timedelta(hours=2)
    while now <= end:
        off = [x for x in fx["official"] if x[0] <= now]
        official = {"status": off[-1][1], "observed_at": off[-1][0], "source": fx["official_source"]} if off else None
        out = run_forecast(fx["levels"], fx["rain"], official, fx["thresholds"], now, location_id=fx["station"])
        out["data_provenance"] = fx["provenance"]
        yield now, out
        now += timedelta(hours=step_hours)
