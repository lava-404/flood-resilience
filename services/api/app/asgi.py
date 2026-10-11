"""uvicorn entrypoint.  REPO=memory -> seeded SYNTHETIC demo with no database; otherwise PostgreSQL (DB_* env)."""
import asyncio, contextlib, logging
from floodcommon import metrics, service
from floodcommon.config import Settings, database_dsn
from .main import create_app

logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
settings = Settings()

if settings.repo == "memory":
    from datetime import datetime
    from ingest.local_demo import run, seed_shelters
    settings.demo_now = settings.demo_now or "2024-09-28T20:00:00+00:00"   # pin the clock inside the SYNTHETIC replay
    repo, _ = run(step_hours=1, until=datetime.fromisoformat(settings.demo_now))
    seed_shelters(repo)
else:
    from floodcommon.pgrepo import PgRepo
    repo = PgRepo(database_dsn())


async def _publish_ops():
    clock = settings.clock()
    while True:
        try:
            m = service.ops_metrics(repo, clock())
            metrics.put("ForecastAgeMinutes", m["forecast_age_minutes"], "None", enabled=settings.metrics_enabled)
            for src, age in m["source_age_minutes"].items():
                metrics.put("SourceAgeMinutes", age, "None", {"Source": src}, settings.metrics_enabled)
        except Exception: logging.exception("ops metrics failed")
        await asyncio.sleep(300)


@contextlib.asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_publish_ops()) if settings.metrics_enabled else None
    yield
    if task: task.cancel()

app = create_app(repo, settings)
app.router.lifespan_context = lifespan
