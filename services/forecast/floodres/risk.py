"""Risk-state mapping and official-warning safety rules (SRS 8.5, 14.1)."""
STATES = ["SAFE", "WATCH", "WARNING", "EVACUATE"]
RANK = {s: i for i, s in enumerate(STATES)}
# Floor imposed by an official warning. Configurable; 'severe' -> WARNING is a conservative-but-not-
# maximal choice that should be reviewed with domain experts.
OFFICIAL_FLOOR = {"normal": "SAFE", "watch": "WATCH", "warning": "WARNING", "severe": "WARNING"}
CONF = ["low", "medium", "high"]


def model_state(last, central, q90, slope, rain6h, th):
    """Map forecast to a state. Uses q90 only to escalate to WATCH (conservative)."""
    peak = max(central.values())
    q90_peak = max(q90.values())
    if peak >= th["danger"]:
        return "EVACUATE"
    if peak >= th["warning"]:
        return "WARNING"
    near = last >= 0.8 * th["warning"]
    if q90_peak >= th["warning"] or (slope > 0.05 and near) or (rain6h >= 40 and slope > 0 and near):
        return "WATCH"
    return "SAFE"


def apply_official(state, official_status):
    """Official warnings can raise the state but never be silently lowered. Returns (state, note)."""
    if official_status is None:
        return state, None
    floor = OFFICIAL_FLOOR.get(official_status, "SAFE")
    if RANK[floor] > RANK[state]:
        return floor, {
            "code": "official_floor_applied",
            "message": f"Official warning active ({official_status}); model-only state was {state}.",
            "model_state": state,
        }
    return state, None


def cap_confidence(conf, ceiling):
    return CONF[min(CONF.index(conf), CONF.index(ceiling))]
