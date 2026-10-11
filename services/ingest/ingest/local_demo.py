"""Runs ingest -> queue -> forecast worker in memory over the SYNTHETIC replay. Verifiable without AWS/Docker.
    PYTHONPATH=services/common:services/forecast:services/ingest python3 -m ingest.local_demo"""
import json, os, tempfile
from datetime import datetime, timedelta, timezone
from floodcommon.ports import InMemoryQueue, LocalSnapshotStore
from floodcommon.repo import InMemoryRepo
from floodres.worker import handle_job
from .adapters import FixtureAdapter
from .pipeline import run_ingestion

FIX = "data/fixtures/replay_sep2024_SYNTHETIC.json"


def _load(path):
    with open(path) as f: return json.load(f)


def seed_shelters(repo, path="data/fixtures/shelters_DEMO.json"):
    repo.add_shelters(_load(path)["shelters"])


def run(step_hours=6, repo=None, until=None):
    repo, queue = repo or InMemoryRepo(), InMemoryQueue()
    snaps = LocalSnapshotStore(tempfile.mkdtemp())
    t0 = datetime(2024, 9, 27, 2, tzinfo=timezone.utc)
    now, rows = t0, []
    end = until or datetime(2024, 9, 29, 8, tzinfo=timezone.utc)
    while now <= end:
        run_ingestion(FixtureAdapter(FIX, as_of=now), repo, snaps, queue, now)
        for job in queue.drain():
            handle_job(job, repo, datetime.fromisoformat(job["as_of"]))
        r = repo.latest_risk("DEMO-KOSI-01")
        rows.append((now, r["state"], r["confidence"], r["live"]))
        now += timedelta(hours=step_hours)
    return repo, rows


if __name__ == "__main__":
    for t, s, c, live in run()[1]:
        print(t.strftime("%d %H:%M"), s.ljust(8), c.ljust(6), "live" if live else "NOT-LIVE")
