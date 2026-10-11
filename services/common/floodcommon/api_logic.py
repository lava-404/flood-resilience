"""Framework-free endpoint logic (SRS 13.3). Used by BOTH the FastAPI app (services/api/app/main.py) and the dependency-free dev
server (scripts/dev_server.py), so it is exercised by real HTTP tests in this repo. Raises ApiError(status, detail)."""
import base64, json, logging, uuid
from datetime import timedelta
from . import envelope, policy, security, service
from .envelope import REPORT_TYPES
from .util import haversine_km

log = logging.getLogger("floodres.api")
REPLAY_EVENTS = {"sep2024-synthetic": "data/fixtures/replay_sep2024_SYNTHETIC.json"}
MAX_BODY_BYTES = 64 * 1024


class ApiError(Exception):
    def __init__(self, status, detail): super().__init__(str(detail)); self.status, self.detail = status, detail


def _coord(lat, lon):
    try: lat, lon = float(lat), float(lon)
    except (TypeError, ValueError): raise ApiError(422, "lat/lon must be numbers")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ApiError(422, "lat/lon out of range")
    return lat, lon


def _risk_for(repo, st, now, lat, lon):
    lat, lon = _coord(lat, lon)
    s = repo.nearest_station(lat, lon)
    d = haversine_km(lat, lon, s.lat, s.lon) if s else None
    if s is None or d > st.max_station_km:
        raise ApiError(404, "no monitored river station within range; no forecast is available for this location")
    r = service.freshen(repo.latest_risk(s.id), now)
    if r is None: raise ApiError(503, "no forecast has been generated yet for this location")
    return s, d, r


def clock_label(st): return "demo" if st.demo_now else "wall"


def risk(repo, st, now, lat, lon):
    s, d, r = _risk_for(repo, st, now, lat, lon)
    return {"state": r["state"], "confidence": r["confidence"], "confidence_reasons": r.get("confidence_reasons", []),
            "generated_at": r["forecast_generated_at"], "data_cutoff": r.get("data_cutoff"), "model_version": r["model_version"],
            "live": r["live"], "expired": r["expired"], "age_minutes": r["age_minutes"], "forecast": r.get("forecast"),
            "interval_method": r.get("interval_method"), "drivers": r.get("drivers", []), "official": r.get("official"),
            "override": r.get("override"), "conflict": r.get("conflict", False), "source_freshness": r.get("source_freshness"),
            "provenance": r.get("provenance"), "data_provenance": r.get("data_provenance"),
            "station": {"id": s.id, "name": s.name, "distance_km": round(d, 1)}, "clock": clock_label(st)}


def timeline(repo, st, now, lat, lon, hours=24):
    s, _, _ = _risk_for(repo, st, now, lat, lon)
    hist = [{"generated_at": h["forecast_generated_at"], "state": h["state"], "confidence": h["confidence"], "current_level_m": h.get("current_level_m"),
             "q50_3h": (h.get("forecast") or {}).get("3h", {}).get("q50")}
            for h in repo.risk_history(s.id, 72) if (now - h["forecast_generated_at"]) <= timedelta(hours=hours)]
    rain = [{"observed_at": o.observed_at, "mm_per_h": o.value, "provenance": o.provenance}
            for o in repo.observations(s.id, "rainfall", now) if (now - o.observed_at) <= timedelta(hours=hours)]
    return {"station": s.id, "history": hist, "rainfall": rain}


def stations_nearby(repo, lat, lon, radius_km=50):
    lat, lon = _coord(lat, lon)
    return [{"id": s.id, "name": s.name, "basin": s.basin, "lat": s.lat, "lon": s.lon, "distance_km": d, "provenance": s.provenance}
            for d, s in repo.stations_nearby(lat, lon, min(float(radius_km), 200))]


def flood_extent():
    return {"available": False, "reason": "no precomputed inundation scenarios are loaded", "type": "FeatureCollection", "features": []}


def shelters(repo, lat, lon, radius_km=25):
    lat, lon = _coord(lat, lon); return repo.shelters_nearby(lat, lon, min(float(radius_km), 100))


def post_report(repo, now, b):
    lat, lon = _coord(b.get("lat"), b.get("lon"))
    rid, reporter = str(b.get("id") or uuid.uuid4())[:64], b.get("reporter_id")
    if not isinstance(reporter, str) or not (0 < len(reporter) <= 64): raise ApiError(422, "reporter_id required (<= 64 chars)")
    if b.get("type") not in REPORT_TYPES: raise ApiError(422, "unknown report type")
    note = b.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > 280): raise ApiError(422, "note too long")
    v = b.get("value")
    if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))): raise ApiError(422, "value must be a number")
    if repo.count_by_peer(reporter, now - timedelta(hours=1)) >= policy.PEER_QUOTA_PER_HOUR: raise ApiError(429, "report quota exceeded")
    repo.add_report({"id": rid, "reporter_id": reporter, "type": b["type"], "lat": lat, "lon": lon, "value": v, "note": note,
                     "created_at": now, "expires_at": now + timedelta(hours=12), "received_at": now, "verification_state": "unverified"})
    return {"id": rid, "verification_state": "unverified"}


def reports_nearby(repo, now, lat, lon, radius_km=25):
    lat, lon = _coord(lat, lon)
    return [{k: v for k, v in r.items() if k != "reporter_id"} for r in repo.list_reports()
            if r["expires_at"] > now and haversine_km(lat, lon, r["lat"], r["lon"]) <= min(float(radius_km), 100)]


def _store(repo, st, now, e, via):
    r = policy.accept_message(repo, e, via, now, check_signature=st.require_signature)
    log.info("message %s id=%s", r["status"], r["message_id"])           # never log payload or location
    return r


def post_sos(repo, st, now, e):
    if not isinstance(e, dict) or e.get("message_type") != "SOS": raise ApiError(422, {"problems": ["not_an_sos"]})
    r = _store(repo, st, now, e, "direct")
    if r["status"] == "rejected": raise ApiError(422, r)
    if r["status"] == "rate_limited": raise ApiError(429, r)
    return r


def peer_sync(repo, st, now, body):
    msgs = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(msgs, list) or len(msgs) > 50: raise ApiError(422, "messages must be a list of at most 50")
    results = [_store(repo, st, now, e, "gateway") for e in msgs]
    return {"results": results, "states": repo.sos_states([r["message_id"] for r in results if r["message_id"]])}


def sos_status(repo, ids): return repo.sos_states([i for i in (ids or "").split(",")[:100] if i])


def source_health(repo, now): return service.source_health_view(repo.source_health_rows(), now)


def replay(event_id, step_hours=3):
    if event_id not in REPLAY_EVENTS: raise ApiError(404, "unknown replay event")
    from floodres import replay as rp
    fx = rp.load(REPLAY_EVENTS[event_id])
    return {"event_id": event_id, "synthetic": True, "notice": "SYNTHETIC reconstruction for demonstration. Not real observations.",
            "steps": [{"at": t, **{k: o[k] for k in ("state", "confidence", "live", "forecast", "official", "override", "drivers", "source_freshness")}}
                      for t, o in rp.replay(fx, max(1, min(int(step_hours), 12)))]}


class ResponderAuth:
    def __init__(self, token): self.token, self.limiter = token, security.FailureLimiter()

    def check(self, headers, fallback_ip):
        """headers: dict with LOWER-CASE keys."""
        if not security.token_acceptable(self.token): raise ApiError(503, "responder access not configured")     # fail closed
        key = security.client_key(headers, fallback_ip)
        if self.limiter.blocked(key): raise ApiError(429, "too many failed attempts; try again later")
        if not security.tokens_equal((headers.get("authorization") or "").removeprefix("Bearer ").strip(), self.token):
            self.limiter.record_failure(key); log.warning("AUDIT responder_auth_failed"); raise ApiError(401, "unauthorized")
        self.limiter.reset(key)


def responder_sos(repo):
    out = []
    for s in repo.list_sos():
        e = s.get("envelope") or {}
        note = json.loads(base64.b64decode(e["payload_b64"])).get("note") if e.get("payload_b64") else None
        out.append({**{k: s[k] for k in ("message_id", "lat", "lon", "people_count", "medical_flag", "severity", "created_at", "expires_at", "hop_count", "received_via", "state")}, "note": note})
    return out


def ack(repo, mid):
    if not repo.set_sos_state(mid, "acknowledged"): raise ApiError(404, "unknown message")
    log.info("AUDIT sos_acknowledged id=%s", mid)
    return {"message_id": mid, "state": "acknowledged"}


def overview(repo, st, now):
    keep = ("state", "confidence", "live", "expired", "age_minutes", "official", "conflict", "override", "data_provenance")
    return {"as_of": now, "clock": clock_label(st),
            "risks": [{"station": s.id, "name": s.name, "lat": s.lat, "lon": s.lon, **{k: v for k, v in (service.freshen(repo.latest_risk(s.id), now) or {}).items() if k in keep}} for s in repo.list_stations()],
            "source_health": service.source_health_view(repo.source_health_rows(), now), "ops": service.ops_metrics(repo, now)}
