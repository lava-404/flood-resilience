#!/usr/bin/env python3
"""End-to-end check of the REAL stack (FastAPI + PostgreSQL/PostGIS + SQS worker via docker compose). Stdlib + `cryptography`.
WRITTEN BUT NEVER EXECUTED by its author (no Docker/network where it was written). Run:  scripts/up_local.sh
Exit code 0 only if every check passes. Env: API_URL, RESPONDER_TOKEN, DEMO_NOW."""
import base64, json, os, sys, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

API = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.environ.get("RESPONDER_TOKEN", "local-responder-token-0123456789")
LAT, LON = 26.15, 85.90
results = []


def http(method, path, body=None, headers=None, timeout=15):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(API + path, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read();
        try: return e.code, json.loads(raw)
        except Exception: return e.code, {"raw": raw[:200].decode(errors="replace")}


def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}")); return bool(cond)


def wait(path, ok=lambda s, j: s == 200, seconds=120):
    end, last = time.time() + seconds, None
    while time.time() < end:
        try:
            s, j = http("GET", path); last = (s, j)
            if ok(s, j): return s, j
        except Exception as e: last = ("exc", str(e))
        time.sleep(2)
    return last


def env(sk, mid, now, mtype="SOS", payload=None, hop=0, ttl_h=24):
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = payload if payload is not None else ({"people_count": 2, "medical": True, "note": "e2e"} if mtype == "SOS" else {"type": "blocked_road"})
    e = {"protocol_version": 1, "message_id": mid, "origin_peer_id": sk.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw).hex(),
         "message_type": mtype, "created_at": iso(now), "expires_at": iso(now + timedelta(hours=ttl_h)), "hop_count": hop, "max_hops": 5,
         "lat_e4": 261500, "lon_e4": 859000, "severity": 3, "payload_b64": base64.b64encode(json.dumps(payload).encode()).decode()}
    msg = "\n".join(["FR1", "1", e["message_id"], e["origin_peer_id"], mtype, e["created_at"], e["expires_at"], "5", "261500", "859000", "3", e["payload_b64"]])
    e["signature"] = sk.sign(msg.encode()).hex(); return e


def main():
    s, j = wait("/healthz"); check("healthz", s == 200 and j.get("status") == "ok", (s, j))
    s, j = wait("/readyz", seconds=60); check("readyz (database reachable)", s == 200, (s, j))
    s, risk = wait(f"/v1/risk?lat={LAT}&lon={LON}", seconds=180)
    if not check("seeded forecast is served from PostgreSQL", s == 200, (s, risk)): return summary()

    check("risk has state/confidence/timestamps/model version", risk["state"] in ("SAFE", "WATCH", "WARNING", "EVACUATE") and risk["confidence"] in ("low", "medium")
          and risk["generated_at"] and risk["data_cutoff"] and risk["model_version"], risk)
    f = risk["forecast"]
    check("1h/3h/6h forecasts with ordered uncertainty bounds", f and all(f[h]["q10"] <= f[h]["q50"] <= f[h]["q90"] for h in ("1h", "3h", "6h")), f)
    check("uncertainty is labelled uncalibrated; confidence never 'high'", risk["interval_method"] == "heuristic_uncalibrated" and risk["confidence"] != "high", risk)
    check("synthetic provenance and demo clock are disclosed", risk["data_provenance"] == "synthetic_reconstruction" and risk["clock"] == "demo", risk)
    check("freshness fields present", isinstance(risk["live"], bool) and isinstance(risk["age_minutes"], int) and "source_freshness" in risk, risk)
    demo = risk["clock"] == "demo"
    now = datetime.fromisoformat(os.environ.get("DEMO_NOW", "2024-09-28T20:00:00+00:00")) if demo else datetime.now(timezone.utc)

    s, rp = http("GET", "/v1/replay/sep2024-synthetic?step_hours=1")
    steps = rp.get("steps", []) if s == 200 else []
    check("replay is labelled synthetic", s == 200 and rp.get("synthetic") is True and "SYNTHETIC" in rp.get("notice", ""), (s, str(rp)[:200]))
    floor = {"watch": 1, "warning": 2, "severe": 2}; rank = {"SAFE": 0, "WATCH": 1, "WARNING": 2, "EVACUATE": 3}
    bad = [x["at"] for x in steps if x.get("official") and x["official"].get("freshness") != "stale" and rank[x["state"]] < floor.get(x["official"]["status"], 0)]
    check("official warnings are never silently downgraded across the replay", steps and not bad, bad[:3])
    stale_live = [x["at"] for x in steps if x["live"] and x["source_freshness"]["river_level"] != "fresh"]
    check("a forecast is only ever 'live' when river data is fresh (never for aging/stale/missing)", steps and not stale_live, stale_live[:3])
    check("the replay actually contains degraded-data hours (so the check above is meaningful)", any(x["source_freshness"]["river_level"] != "fresh" for x in steps))
    check("replay passes through escalation", {"SAFE", "EVACUATE"} <= {x["state"] for x in steps}, sorted({x["state"] for x in steps}))

    s, sh = http("GET", "/v1/source-health")
    check("source health reports the synthetic source", s == 200 and any(x["source"] == "fixture_synthetic" for x in sh), (s, sh))
    s, shel = http("GET", f"/v1/shelters/nearby?lat={LAT}&lon={LON}")
    check("PostGIS shelter query works and is labelled demo", s == 200 and shel and shel[0].get("provenance") == "synthetic_demo", (s, shel))
    check("no station in range -> 404, not a guess", http("GET", "/v1/risk?lat=12.9&lon=77.6")[0] == 404)

    sk = Ed25519PrivateKey.generate(); mid = "e2e-" + str(int(time.time()))
    e = env(sk, mid, now)
    s, j = http("POST", "/v1/sos", e); check("signed SOS accepted", s == 200 and j["status"] == "accepted", (s, j))
    s, j = http("POST", "/v1/sos", e); check("replayed SOS is a duplicate", s == 200 and j["status"] == "duplicate", (s, j))
    check("tampered SOS rejected (422)", http("POST", "/v1/sos", {**env(sk, mid + "t", now), "lat_e4": 1})[0] == 422)
    s, j = http("POST", "/v1/sos", env(sk, mid + "x", now - timedelta(days=3))); check("expired SOS rejected", s == 422 and "expired" in json.dumps(j), (s, j))
    check("schema-invalid payload rejected", http("POST", "/v1/sos", env(sk, mid + "p", now, payload={"people_count": "many"}))[0] == 422)
    s, j = http("POST", "/v1/peer/sync", {"messages": [env(sk, mid + "r", now, "REPORT")]}); check("gateway sync routes a REPORT", s == 200 and j["results"][0]["status"] == "accepted", (s, j))
    s, j = http("GET", f"/v1/sos/status?ids={mid}"); check("SOS state is persisted in the database", j.get(mid) == "received", (s, j))
    s, j = http("POST", "/v1/peer/sync", {"messages": [env(sk, mid, now, hop=4)]}); check("duplicate at higher hop_count accepted as duplicate", s == 200 and j["results"][0]["status"] == "duplicate", (s, j))

    flood = Ed25519PrivateKey.generate(); codes = [http("POST", "/v1/sos", env(flood, f"q{i}-{mid}", now))[0] for i in range(24)]
    check("per-peer quota: first 20 accepted, then 429", codes[:20] == [200] * 20 and 429 in codes[20:], codes)

    H = {"Authorization": "Bearer " + TOKEN}
    check("responder API requires a token", http("GET", "/v1/responder/sos")[0] in (401, 503))
    s, j = http("GET", "/v1/responder/sos", headers=H); check("responder sees the SOS", s == 200 and any(x["message_id"] == mid for x in j), (s, str(j)[:200]))
    s, j = http("GET", "/v1/responder/overview", headers=H); check("overview includes risks, source health, ops", s == 200 and j["risks"] and "source_health" in j and "ops" in j, (s, str(j)[:200]))
    s, j = http("POST", f"/v1/responder/sos/{mid}/ack", headers=H); check("responder acknowledges", s == 200, (s, j))
    s, j = http("GET", f"/v1/sos/status?ids={mid}"); check("acknowledgement visible to the device", j.get(mid) == "acknowledged", (s, j))
    codes = [http("GET", "/v1/responder/sos", headers={"Authorization": "Bearer wrong-" + str(i)})[0] for i in range(7)]
    check("responder lockout after repeated failures (run last)", 429 in codes, codes)
    summary()


def summary():
    n, p = len(results), sum(results); print(f"\n{p}/{n} checks passed"); sys.exit(0 if p == n and n > 0 else 1)


if __name__ == "__main__":
    main()
