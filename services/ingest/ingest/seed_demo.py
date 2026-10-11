"""Seeds PostgreSQL with the SYNTHETIC replay through the SAME code path the tests exercise (local_demo.run).
    DEMO_AS_OF=2024-09-28T20:00:00+00:00 python -m ingest.seed_demo      (needs DB_* env; UNTESTED against a live database)"""
import os
from datetime import datetime
from floodcommon.config import database_dsn
from floodcommon.pgrepo import PgRepo
from . import local_demo

repo = PgRepo(database_dsn())
end = datetime.fromisoformat(os.environ.get("DEMO_AS_OF", "2024-09-28T20:00:00+00:00"))
local_demo.run(step_hours=1, repo=repo, until=end)
local_demo.seed_shelters(repo)
print("seeded SYNTHETIC replay up to", end.isoformat())
