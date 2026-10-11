"""Read-time freshness rules and source-health view. A stale/failed pipeline must LOWER freshness, never fake live."""
from datetime import timedelta

FORECAST_STALE_AFTER = timedelta(minutes=90)
FORECAST_EXPIRED_AFTER = timedelta(hours=6)
SOURCE_STALE_AFTER = timedelta(hours=3)


def freshen(result, now):
    if result is None: return None
    out = dict(result)
    age = now - out["forecast_generated_at"]
    out["age_minutes"] = int(age.total_seconds() // 60)
    reasons = list(out.get("confidence_reasons", []))
    if age > FORECAST_STALE_AFTER:
        out["live"] = False
        out["confidence"] = "low"
        if "forecast_overdue" not in reasons: reasons.append("forecast_overdue")
    out["expired"] = age > FORECAST_EXPIRED_AFTER      # state is kept (never silently dropped) but flagged
    out["confidence_reasons"] = reasons
    return out


def source_health_view(rows, now):
    out = []
    for r in rows:
        ok, last = r["last_success"], r["last_run"]
        age = (now - ok["finished_at"]) if ok else None
        if ok is None: state = "never_succeeded"
        elif last["status"] != "success": state = "failing"
        elif age > SOURCE_STALE_AFTER: state = "stale"
        else: state = "ok"
        out.append({"source": r["source"], "state": state,
                    "last_success_at": ok["finished_at"] if ok else None,
                    "last_observed_at": ok.get("last_observed_at") if ok else None,
                    "last_status": last["status"], "last_error": last.get("error"),
                    "record_count": last.get("records", 0),
                    "age_minutes": int(age.total_seconds() // 60) if age is not None else None})
    return out


def ops_metrics(repo, now):
    """Values for CloudWatch alarms (SRS FR-21). 9999 = 'never'; alarms treat that as breaching."""
    ages = [(now - r["forecast_generated_at"]).total_seconds() / 60
            for r in (repo.latest_risk(s.id) for s in repo.list_stations()) if r]
    srcs = {h["source"]: (h["age_minutes"] if h["age_minutes"] is not None else 9999)
            for h in source_health_view(repo.source_health_rows(), now)}
    return {"forecast_age_minutes": max(ages) if ages else 9999, "source_age_minutes": srcs}
