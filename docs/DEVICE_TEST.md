# Two-phone offline SOS relay test (NOT YET PERFORMED: this is the procedure and the pass criteria)

Equipment: two physical Android phones (A, B; Android 8+, Wi-Fi Direct capable; ideally one Android 13+ and one older), USB cables, a Mac with `adb`, ideally a third phone C. Build/installation: `docs/MACOS_SETUP.md` section 4. Use the SAME debug APK on both.

## A. Prepare
```bash
adb devices -l                                   # note both serials: A_SER, B_SER
adb -s $A_SER install -r app-debug.apk && adb -s $B_SER install -r app-debug.apk
for s in $A_SER $B_SER; do adb -s $s logcat -c; done
adb -s $A_SER logcat -s FloodP2p:I ReactNativeJS:W > /tmp/A.log &    # two terminals/background jobs
adb -s $B_SER logcat -s FloodP2p:I ReactNativeJS:W > /tmp/B.log &
```
Start the local API only for step E: `REPO=memory RESPONDER_TOKEN=... uvicorn app.asgi:app --host 0.0.0.0 --port 8000` plus `adb -s $B_SER reverse tcp:8000 tcp:8000`.
Open the app on both phones, grant "Nearby devices" (Android 13+) or Location (<= 12). Keep both screens on and apps in the foreground (there is no background service yet).

## B. Isolate from the internet
Both phones: airplane mode ON, then Wi-Fi ON (Wi-Fi Direct needs Wi-Fi on, not a connected network). Disconnect from any access point. Cellular off.
**Pass:** Home shows "Saved information"/offline banner, never "Live".

## C. Discovery  (allow up to ~2 minutes; discovery cycles every ~60 s)
**Pass:** SOS tab on each phone shows "1 nearby device"; logs contain `wifi-direct found fr-...` and `hello from <peer8>`.
**If not:** toggle Wi-Fi on both; accept any system "Invitation to connect" dialog; move phones within 2 m; check permissions in system settings; read `/tmp/*.log` for `exchange failed`.

## D. Relay
A: SOS tab -> people 2 -> Send SOS.
**Pass:** A lists "Saved on this phone" immediately (no network needed), then "Passed to a nearby phone"; B log: `exchange done ... received=1`; B's `adb shell run-as` not required: confirm via B's Reports/SOS state or the log.
Negative checks: tap Send twice -> B still holds one copy (dedup); wait past expiry (24 h) or use a short TTL build -> not relayed; airplane-mode toggle mid-exchange -> no crash.

## E. Delivery to the responder console
Give B internet (disable airplane mode; Wi-Fi to the same LAN as the Mac or use `adb reverse`; set `API_BASE` accordingly in a debug build). Open the responder console.
**Pass:** the SOS appears once with `via gateway`, `hop_count` >= 1; clicking Acknowledge changes it; A shows "Responders acknowledged" after A or B syncs with the API.

## F. Three-device dedup (if you have phone C)
A meets B and C; B and C both go online. **Pass:** exactly one dashboard row.

## Record
Phone models, Android versions, time per step, and any failures with the matching log lines. Treat any failure as expected first-run debugging: the Kotlin module has never run on hardware. Known limits: foreground only, one Wi-Fi Direct group at a time, signed but not encrypted payloads, BLE fallback absent.
