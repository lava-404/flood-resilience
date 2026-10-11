"""Data-quality gate: staleness, range and rate-of-change checks (SRS 8.2 step 2, FR-07)."""
from datetime import datetime, timedelta

# Source-specific freshness limits. Demo defaults; tune per source once feeds are verified.
STALE_LIMITS = {
    "river_level": timedelta(hours=3),
    "rainfall": timedelta(hours=2),
    "official": timedelta(hours=12),
}
OFFICIAL_MAX_AGE = timedelta(hours=48)   # beyond this a last-known warning is no longer applied, and that is shown explicitly
MAX_RATE_M_PER_H = 1.0   # physically implausible river rise/fall above this (demo value)
MIN_LEVEL, MAX_LEVEL = -1.0, 60.0


def age(obs_time: datetime | None, now: datetime) -> timedelta | None:
    return None if obs_time is None else now - obs_time


def freshness(obs_time: datetime | None, now: datetime, kind: str) -> str:
    """'missing' | 'fresh' | 'aging' (>50% of limit) | 'stale'."""
    a = age(obs_time, now)
    if a is None:
        return "missing"
    limit = STALE_LIMITS[kind]
    if a > limit:
        return "stale"
    return "aging" if a > limit / 2 else "fresh"


def screen_levels(series):
    """series: [(datetime, float)] sorted. Returns (clean, flags).
    Out-of-range values and impossible jumps are dropped from `clean` and listed in `flags`."""
    clean, flags = [], []
    for t, v in series:
        if v is None or not (MIN_LEVEL <= v <= MAX_LEVEL):
            flags.append({"observed_at": t, "reason": "out_of_range", "value": v})
            continue
        if clean:
            dt_h = (t - clean[-1][0]).total_seconds() / 3600
            if dt_h > 0 and abs(v - clean[-1][1]) / dt_h > MAX_RATE_M_PER_H:
                flags.append({"observed_at": t, "reason": "implausible_rate", "value": v})
                continue
        clean.append((t, v))
    return clean, flags
