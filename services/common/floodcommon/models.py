from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Station:
    id: str
    source: str
    name: str
    basin: str
    lat: float
    lon: float
    parameter: str
    threshold_warning: float
    threshold_danger: float
    provenance: str = "observed"   # 'observed' | 'synthetic_reconstruction'


@dataclass(frozen=True)
class Observation:
    station_id: str
    parameter: str                 # river_level | rainfall | official_status
    observed_at: datetime
    received_at: datetime
    source: str
    value: float | None = None
    text_value: str | None = None
    unit: str | None = None
    quality_flag: str = "ok"
    provenance: str = "observed"
