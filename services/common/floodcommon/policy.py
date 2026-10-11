"""Accept/reject pipeline for SOS and REPORT envelopes: validation -> replay/duplicate -> quota -> persist.
Pure over the repository port so it is tested without FastAPI."""
import base64, json
from datetime import timedelta
from . import envelope

PEER_QUOTA_PER_HOUR = 20


def _mid(e):
    m = e.get("message_id") if isinstance(e, dict) else None
    return m[:64] if isinstance(m, str) else None


def accept_message(repo, e, via, now, *, check_signature=True, quota=PEER_QUOTA_PER_HOUR):
    """status: accepted | duplicate | rejected (permanent, do not retry) | rate_limited (transient, retry later)."""
    probs = envelope.validate(e, now, check_signature)
    if probs: return {"message_id": _mid(e), "status": "rejected", "problems": probs}
    mid = e["message_id"]
    if repo.has_message(mid):
        repo.lower_hop_count(mid, e["hop_count"])   # hop_count is unsigned: keep the LOWEST seen so a forged high count can't win
        return {"message_id": mid, "status": "duplicate", "problems": []}
    if repo.count_by_peer(e["origin_peer_id"], now - timedelta(hours=1)) >= quota:
        return {"message_id": mid, "status": "rate_limited", "problems": ["peer_quota"]}
    p = json.loads(base64.b64decode(e["payload_b64"]))
    c, x = envelope._pt(e["created_at"]), envelope._pt(e["expires_at"])
    lat, lon = e["lat_e4"] / 1e4, e["lon_e4"] / 1e4
    if e["message_type"] == "REPORT":
        ok = repo.add_report({"id": mid, "reporter_id": e["origin_peer_id"], "type": p["type"], "lat": lat, "lon": lon, "value": p.get("value"),
                              "note": p.get("note"), "created_at": c, "expires_at": x, "received_at": now, "verification_state": "unverified"})
    else:
        ok = repo.add_sos({"message_id": mid, "origin_peer_id": e["origin_peer_id"], "lat": lat, "lon": lon, "people_count": p.get("people_count"),
                           "medical_flag": bool(p.get("medical")), "severity": e["severity"], "created_at": c, "expires_at": x, "hop_count": e["hop_count"],
                           "received_via": via, "received_at": now, "state": "received", "envelope": e})
    return {"message_id": mid, "status": "accepted" if ok else "duplicate", "problems": []}
