"""Regenerates data/fixtures/envelope_vector.json. Uses a PUBLIC, TEST-ONLY seed (never a real key)."""
import base64, json, os, sys
from datetime import datetime, timezone
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "services/common"))
from cryptography.hazmat.primitives import serialization as s
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from floodcommon import envelope

seed = bytes([1]) * 32
sk = Ed25519PrivateKey.from_private_bytes(seed)
e = {"protocol_version": 1, "message_id": "vec-0001", "origin_peer_id": sk.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw).hex(),
     "message_type": "SOS", "created_at": "2024-09-28T12:00:00Z", "expires_at": "2024-09-29T12:00:00Z", "hop_count": 0, "max_hops": 5,
     "lat_e4": 261500, "lon_e4": 859000, "severity": 3,
     "payload_b64": base64.b64encode(json.dumps({"people_count": 3, "medical": True, "note": "छत पर / on roof"}, ensure_ascii=False).encode()).decode()}
e["signature"] = sk.sign(envelope.signing_string(e).encode()).hex()
json.dump({"TEST_ONLY_seed_hex": seed.hex(), "now": "2024-09-28T12:30:00Z", "signing_string": envelope.signing_string(e), "envelope": e},
          open(os.path.join(ROOT, "data/fixtures/envelope_vector.json"), "w"), indent=1, ensure_ascii=False)
print("vector written")
