"""Forecast engine: quality gate -> baseline -> uncertainty -> safety rules. Pure and deterministic."""
from datetime import datetime
from . import baseline as bl, quality as q, risk as rk

# Honest ceiling: with no validated calibration, confidence never exceeds 'medium' (SRS 8.5, 14.1).
UNCALIBRATED_CEILING = "medium"


def run_forecast(levels, rain, official, thresholds, now: datetime,
                 model_version="baseline-persistence-trend-0.1", location_id="demo"):
    """levels: [(dt, m)], rain: [(dt, mm_per_h)], official: {"status": str, "observed_at": dt} | None."""
    reasons = []
    clean, flags = q.screen_levels([p for p in sorted(levels) if p[0] <= now])
    rain_in = [p for p in sorted(rain) if p[0] <= now]
    last_t, last_v = (clean[-1] if clean else (None, None))
    lvl_fresh = q.freshness(last_t, now, "river_level")
    rain_fresh = q.freshness(rain_in[-1][0] if rain_in else None, now, "rainfall")
    off_status = official["status"] if official else None
    off_fresh = q.freshness(official["observed_at"], now, "official") if official else "missing"
    rain6 = sum(v for t, v in rain_in if (now - t).total_seconds() <= 6 * 3600) if rain_fresh != "missing" else 0.0

    base = {
        "location_id": location_id, "model_version": model_version,
        "forecast_generated_at": now, "provenance": "model_generated",
        "source_freshness": {"river_level": lvl_fresh, "rainfall": rain_fresh, "official": off_fresh},
        "quality_flags": [{**f, "observed_at": f["observed_at"]} for f in flags],
    }

    # --- No usable river data: fall back to the official baseline only; never fabricate a forecast.
    if lvl_fresh in ("missing", "stale"):
        reasons.append("river_level_" + lvl_fresh)
        floor, exp_note = _floor(official, now)
        state, note = rk.apply_official("SAFE", floor)
        note = note or exp_note
        if floor and off_fresh == "stale": reasons.append("official_stale_floor_kept")
        if not note and off_status is None:
            state = "WATCH"  # unknown is not safe: no data and no official all-clear
            reasons.append("no_data_conservative_watch")
        return {**base, "state": state, "confidence": "low", "confidence_reasons": reasons,
                "data_cutoff": last_t, "live": False, "forecast": None,
                "drivers": [], "official": _official(off_status, official, off_fresh),
                "override": note, "conflict": False}

    slope = bl.trend_per_hour(clean)
    central = bl.damped_trend(last_v, slope)
    age_h = (now - last_t).total_seconds() / 3600
    sp = {h: bl.heuristic_spread(h, slope, age_h) for h in bl.HORIZONS}
    q10 = {h: central[h] - 1.28 * sp[h] for h in sp}
    q90 = {h: central[h] + 1.28 * sp[h] for h in sp}

    m_state = rk.model_state(last_v, central, q90, slope, rain6, thresholds)
    floor, exp_note = _floor(official, now)
    state, note = rk.apply_official(m_state, floor)
    note = note or exp_note
    conflict = bool(off_status and off_fresh != "stale" and
                    rk.RANK[rk.OFFICIAL_FLOOR.get(off_status, "SAFE")] - rk.RANK[m_state] >= 2)

    conf = "high"
    if lvl_fresh == "aging": conf = rk.cap_confidence(conf, "medium"); reasons.append("river_level_aging")
    if rain_fresh in ("missing", "stale"): conf = rk.cap_confidence(conf, "medium"); reasons.append("rainfall_" + rain_fresh)
    if off_fresh == "stale":
        conf = rk.cap_confidence(conf, "medium"); reasons.append("official_stale")
        if floor: reasons.append("official_stale_floor_kept")
    if flags: conf = rk.cap_confidence(conf, "medium"); reasons.append("outliers_dropped")
    if conflict: conf = "low"; reasons.append("model_official_conflict")
    conf = rk.cap_confidence(conf, UNCALIBRATED_CEILING); reasons.append("uncalibrated_baseline_ceiling")

    drivers = [
        {"name": "river_level_trend", "value": round(slope, 3), "unit": "m/h", "observed_at": last_t,
         "direction": "up" if slope > 0.02 else "down" if slope < -0.02 else "flat"},
        {"name": "rainfall_6h", "value": round(rain6, 1), "unit": "mm", "direction": "up" if rain6 >= 20 else "flat"},
        {"name": "level_vs_warning", "value": round(last_v - thresholds["warning"], 2), "unit": "m",
         "direction": "up" if last_v >= thresholds["warning"] else "flat", "observed_at": last_t},
    ]
    return {**base, "state": state, "confidence": conf, "confidence_reasons": reasons,
            "data_cutoff": last_t, "live": age_h <= 1.0, "current_level_m": last_v,
            "forecast": {f"{h}h": {"q10": round(q10[h], 2), "q50": round(central[h], 2), "q90": round(q90[h], 2)}
                         for h in bl.HORIZONS},
            "interval_method": "heuristic_uncalibrated",
            "drivers": drivers, "official": _official(off_status, official, off_fresh),
            "override": note, "conflict": conflict}


def _floor(official, now):
    """(status to enforce | None, visible note | None). A stale feed never silently lowers the state: the last official
    status keeps flooring it for up to 48 h; after that it is dropped WITH an explicit note."""
    if not official: return None, None
    if now - official["observed_at"] > q.OFFICIAL_MAX_AGE:
        return None, {"code": "official_expired_not_applied", "model_state": None,
                      "message": f"Last official status ({official['status']}) is over 48 h old and is no longer applied. Check official sources."}
    return official["status"], None


def _official(status, official, fresh):
    return None if status is None else {"status": status, "observed_at": official["observed_at"],
                                        "freshness": fresh, "source": official.get("source", "UNKNOWN")}
