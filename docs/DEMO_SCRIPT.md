# Demo script (4 min). Say "synthetic" out loud: the replay data is fictional.
Setup: API with `DEMO_NOW` set (or `REPO=memory`), two Android phones with the APK, one laptop on the dashboard. Rehearse the P2P step: it has never been run on devices by the author.

| Time | Do | Say |
|---|---|---|
| 0:00 | Phone A Home (WATCH, "Demo data" banner) | "One state, one reason, one action, with source freshness and confidence. Demo data: a synthetic reconstruction, not real gauges." |
| 0:30 | Tap Why? | "Drivers are plain values with units: river trend, 6 h rain. Confidence is capped at medium because nothing is calibrated." |
| 1:00 | Advance the clock (`DEMO_NOW` +6 h or `/v1/replay/sep2024-synthetic`) and refresh | "WATCH -> WARNING -> EVACUATE. An official warning can raise the state but never be silently lowered." |
| 1:40 | Dashboard: source health + stale/failing state | "If a feed breaks, we show it and lower confidence instead of faking 'live'." |
| 2:00 | Phones A and B: airplane mode, Wi-Fi on. A shows "Saved information" | "Offline: cached guidance, never labelled live." |
| 2:20 | A: SOS tab, Send SOS | "Signed and queued locally first; no AWS involved." |
| 2:50 | Show A "Passed to a nearby phone"; B has the message | "Store-and-forward over Wi-Fi Direct with dedup, expiry and hop limits." |
| 3:20 | B regains internet; dashboard shows the SOS (via gateway, 1 hop); click Acknowledge | "Gateway uploads it once; the responder acknowledges." |
| 3:45 | A shows "Responders acknowledged" | "Closed loop. Limits: needs a chain of devices; relay runs while the app is open." |
