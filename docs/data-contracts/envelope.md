# Signed message envelope v1 (SOS / REPORT)

Shared by Python (`services/common/floodcommon/envelope.py`), TypeScript (`apps/mobile/src/core/envelope.ts`) and the Kotlin transport (which does not parse it).
Cross-language agreement is **tested**: `data/fixtures/envelope_vector.json` is signed by Python; the TS test verifies it and reproduces the identical signature.

| Field | Type | Notes |
|---|---|---|
| protocol_version | int | `1` |
| message_id | string (1-64) | globally unique; dedup key |
| origin_peer_id | 64 hex chars | the sender's Ed25519 **public key** (pseudonymous identity) |
| message_type | `SOS` \| `REPORT` | |
| created_at / expires_at | `YYYY-MM-DDTHH:MM:SSZ` | second precision; TTL <= 72 h |
| hop_count | int | **not signed**: relays increment it |
| max_hops | int <= 8 | signed |
| lat_e4 / lon_e4 | int | degrees x 10^4 (~11 m). Integers avoid float-format differences |
| severity | 1..3 | |
| payload_b64 | base64 of UTF-8 JSON | exactly the bytes the origin produced; never re-serialised. <= 2048 bytes. SOS: `{people_count, medical, note}`; REPORT: `{type, value?, note?}` |
| signature | 128 hex chars | Ed25519 over the signing string |

Signing string = `"FR1\n"` + the following joined by `\n`: protocol_version, message_id, origin_peer_id, message_type, created_at, expires_at, max_hops, lat_e4, lon_e4, severity, payload_b64.

Receivers drop (never relay) messages that are malformed, expired, over the hop limit, forged, or already seen. Confidentiality (X25519/AEAD) from SRS 11 is **not implemented**: payloads are signed, not encrypted.
