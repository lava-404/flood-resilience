# Offline SOS relay

Layers: JS (`apps/mobile/src/core`: validation, signatures, dedup, expiry, hop limits, delivery states; **tested under Node**) over a Kotlin transport (`android-native/.../FloodP2pModule.kt`; **untested, needs devices**).

Wire protocol (TCP :8988, newline-delimited): `HELLO {v,peer,known[]}` -> `MSG <envelope>` x N -> `BYE`. Limits: 16 KB/line, 100 messages, 10 s I/O timeout, 30 s per-host cooldown. Discovery: Wi-Fi Direct DNS-SD `_floodres._tcp` (no router needed) and NsdManager mDNS on a shared LAN. BLE fallback: **not implemented**.

Known limitations (be upfront in the demo)
* **No foreground service:** relay only runs while the app is open. Background/Doze operation is future work.
* Wi-Fi Direct joins one group at a time; some devices show a system consent prompt; discovery cycles every ~60 s, so expect tens of seconds per hop.
* Needs a chain of reachable devices or a gateway with internet; it is not city-wide coverage.
* Payloads are signed, not encrypted.

Two-device verification procedure, expected logs and pass criteria: **`docs/DEVICE_TEST.md`** (not yet performed on hardware).
