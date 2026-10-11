"""Persistence + damped-trend baseline (stage A, SRS 16.1). This is the permanent safety baseline."""
import math
from datetime import timedelta

DAMPING = 0.85          # per-hour geometric damping of the recent trend
TREND_WINDOW = timedelta(hours=3)
HORIZONS = (1, 3, 6)


def trend_per_hour(clean):
    """Slope (m/h) over the last TREND_WINDOW using first/last clean points in the window."""
    if len(clean) < 2:
        return 0.0
    t_end, v_end = clean[-1]
    window = [p for p in clean if t_end - p[0] <= TREND_WINDOW]
    if len(window) < 2:
        return 0.0
    dt = (t_end - window[0][0]).total_seconds() / 3600
    return (v_end - window[0][1]) / dt if dt > 0 else 0.0


def persistence(last_level, horizons=HORIZONS):
    return {h: last_level for h in horizons}


def damped_trend(last_level, slope, horizons=HORIZONS):
    out = {}
    for h in horizons:
        eff = sum(DAMPING ** k for k in range(1, h + 1))
        out[h] = last_level + slope * eff
    return out


def heuristic_spread(h, slope, data_age_h):
    """Heuristic 1-sigma spread in metres. NOT calibrated; used only for qualitative bands."""
    sigma = 0.10 + 0.15 * math.sqrt(h) + 0.30 * abs(slope) * h ** 0.5
    return sigma * (1 + max(data_age_h, 0) / 3)
