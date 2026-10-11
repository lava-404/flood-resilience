"""Signed P2P/SOS envelope v1. Cross-language contract: see docs/data-contracts/envelope.md.
Signature = Ed25519 over the UTF-8 bytes of signing_string(). hop_count is NOT signed (relays mutate it)."""
import base64, json, math, re
from datetime import datetime, timedelta

PROTOCOL_VERSION = 1
TYPES = {"SOS", "REPORT"}
MAX_HOPS_LIMIT = 8
MAX_TTL = timedelta(hours=72)
MAX_PAYLOAD_BYTES = 2048
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
REPORT_TYPES = {"water_depth", "blocked_road", "stranded_person", "bridge_structure"}
MAX_NOTE = 140


def _is_int(v):
    return (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer())


def payload_problems(message_type, payload_b64):
    """Strict schema for the signed payload (unknown keys rejected). Mirrors apps/mobile/src/core/envelope.ts."""
    try:
        p = json.loads(base64.b64decode(payload_b64, validate=True).decode("utf-8"))
    except Exception:
        return ["bad_payload"]
    if not isinstance(p, dict): return ["bad_payload"]
    allowed = {"people_count", "medical", "note"} if message_type == "SOS" else {"type", "value", "note"}
    if set(p) - allowed: return ["bad_payload"]
    note = p.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE): return ["bad_payload"]
    if message_type == "SOS":
        pc, med = p.get("people_count"), p.get("medical")
        if pc is not None and not (_is_int(pc) and 0 <= pc <= 500): return ["bad_payload"]
        if med is not None and not isinstance(med, bool): return ["bad_payload"]
    else:
        v = p.get("value")
        if p.get("type") not in REPORT_TYPES: return ["bad_payload"]
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1000): return ["bad_payload"]
    return []


def signing_string(e):
    return "\n".join(["FR1", str(e["protocol_version"]), e["message_id"], e["origin_peer_id"], e["message_type"],
                      e["created_at"], e["expires_at"], str(e["max_hops"]), str(e["lat_e4"]), str(e["lon_e4"]),
                      str(e["severity"]), e["payload_b64"]])


def _pt(s): return datetime.fromisoformat(s.replace("Z", "+00:00"))


def verify_signature(e) -> bool:
    from cryptography.exceptions import InvalidSignature       # raises ImportError if missing -> fail closed
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(e["origin_peer_id"])).verify(
            bytes.fromhex(e["signature"]), signing_string(e).encode())
        return True
    except (InvalidSignature, ValueError):
        return False


def validate(e, now, check_signature=True):
    """Returns list of problems ([] = acceptable). Expired/over-hop/duplicate handling is the caller's job."""
    p = []
    try:
        if e.get("protocol_version") != PROTOCOL_VERSION: p.append("bad_protocol_version")
        if e.get("message_type") not in TYPES: p.append("bad_type")
        if not _HEX64.match(str(e.get("origin_peer_id", ""))): p.append("bad_peer_id")
        if not (0 < len(str(e.get("message_id", ""))) <= 64): p.append("bad_message_id")
        c, x = _pt(e["created_at"]), _pt(e["expires_at"])
        if x <= c or x - c > MAX_TTL: p.append("bad_ttl")
        if now >= x: p.append("expired")
        if c > now + timedelta(minutes=10): p.append("created_in_future")
        if not (0 <= e["hop_count"] <= e["max_hops"] <= MAX_HOPS_LIMIT): p.append("bad_hops")
        if not (-900000 <= e["lat_e4"] <= 900000 and -1800000 <= e["lon_e4"] <= 1800000): p.append("bad_location")
        if len(base64.b64decode(e["payload_b64"], validate=True)) > MAX_PAYLOAD_BYTES: p.append("payload_too_large")
        if e.get("severity") not in (1, 2, 3): p.append("bad_severity")
        if e.get("message_type") in TYPES and "payload_too_large" not in p: p += payload_problems(e["message_type"], e["payload_b64"])
    except (KeyError, ValueError, TypeError, AttributeError):
        return ["malformed"]
    if not p and check_signature and not verify_signature(e): p.append("bad_signature")
    return p
