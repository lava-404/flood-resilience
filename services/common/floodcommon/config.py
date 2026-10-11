import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

_env = lambda k, d="": field(default_factory=lambda: os.getenv(k, d))      # read at INSTANTIATION, not import


@dataclass
class Settings:
    repo: str = _env("REPO", "pg")                          # 'pg' | 'memory' (memory = seeded SYNTHETIC demo, no database)
    responder_token: str = _env("RESPONDER_TOKEN")          # from Secrets Manager in AWS; empty/weak => responder API returns 503
    require_sos_signature_off: bool = field(default_factory=lambda: os.getenv("REQUIRE_SOS_SIGNATURE", "1") == "0")
    cors_origins: list = field(default_factory=lambda: [o for o in os.getenv("CORS_ORIGINS", "").split(",") if o])
    demo_now: str = _env("DEMO_NOW")                        # e.g. 2024-09-28T20:00:00+00:00 pins the clock inside the replay
    max_station_km: float = field(default_factory=lambda: float(os.getenv("MAX_STATION_KM", "50")))
    metrics_enabled: bool = field(default_factory=lambda: os.getenv("METRICS_ENABLED", "0") == "1")

    @property
    def require_signature(self) -> bool:
        return not self.require_sos_signature_off

    def clock(self):
        if self.demo_now:
            t = datetime.fromisoformat(self.demo_now)
            return lambda: t
        return lambda: datetime.now(timezone.utc)


def database_dsn():
    if os.getenv("DATABASE_URL"): return os.environ["DATABASE_URL"]
    e = os.environ
    return (f"host={e['DB_HOST']} port={e.get('DB_PORT', '5432')} dbname={e.get('DB_NAME', 'floodres')} "
            f"user={e['DB_USER']} password={e['DB_PASSWORD']} sslmode={e.get('DB_SSLMODE', 'require')}")
