"""One-shot ingestion task (run by EventBridge Scheduler -> ECS Fargate). UNTESTED against AWS.
Exit code != 0 on any non-success so ECS shows a failed task. Env: ADAPTER, SNAPSHOT_BUCKET, FORECAST_QUEUE_URL, DB_*"""
import logging, os, sys
from datetime import datetime, timezone
from floodcommon import metrics
from floodcommon.config import database_dsn
from floodcommon.pgrepo import PgRepo
from floodcommon.ports import S3SnapshotStore, SqsQueue
from .adapters import REGISTRY
from .pipeline import run_ingestion

logging.basicConfig(level=logging.INFO)
name = os.environ.get("ADAPTER", "fixture")
adapter = REGISTRY[name](os.environ["FIXTURE_PATH"]) if name == "fixture" else REGISTRY[name]()
now = datetime.fromisoformat(os.environ["DEMO_NOW"]) if os.getenv("DEMO_NOW") else datetime.now(timezone.utc)
if name == "fixture" and os.getenv("DEMO_NOW"): adapter.as_of = now      # replay: reveal the fixture only up to the demo clock
run = run_ingestion(adapter, PgRepo(database_dsn()), S3SnapshotStore(os.environ["SNAPSHOT_BUCKET"]),
                    SqsQueue(os.environ["FORECAST_QUEUE_URL"]), now)
logging.info("ingestion run_id=%s source=%s status=%s records=%s error=%s", run["run_id"], run["source"], run["status"], run["records"], run["error"])
metrics.put("IngestionFailure", 0 if run["status"] == "success" else 1, dims={"Source": run["source"]})
sys.exit(0 if run["status"] == "success" else 1)
