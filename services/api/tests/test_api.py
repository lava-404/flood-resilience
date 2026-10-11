"""API tests (pytest + fastapi TestClient). WRITTEN BUT NOT EXECUTED: fastapi/httpx were not installable in the authoring environment.
Run from repo root:  PYTHONPATH=services/common:services/forecast:services/ingest:services/api pytest services/api/tests -q"""
import base64, json
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from floodcommon import envelope
from floodcommon.config import Settings
from ingest import local_demo
from app.main import create_app

NOW = datetime(2024, 9, 28, 20, tzinfo=timezone.utc)
LAT, LON = 26.15, 85.90


@pytest.fixture(scope="module")
def repo():
    r, _ = local_demo.run(step_hours=1, until=NOW)
    local_demo.seed_shelters(r)
    return r


def client(repo, now=NOW, token="t" * 32):
    return TestClient(create_app(repo, Settings(responder_token=token), lambda: now))


def signed(sk, mid="m1", now=NOW):
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    e = {"protocol_version": 1, "message_id": mid, "origin_peer_id": sk.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw).hex(),
         "message_type": "SOS", "created_at": iso(now), "expires_at": iso(now + timedelta(hours=24)), "hop_count": 1, "max_hops": 5,
         "lat_e4": 261500, "lon_e4": 859000, "severity": 3,
         "payload_b64": base64.b64encode(json.dumps({"people_count": 2, "medical": False, "note": "roof"}).encode()).decode()}
    e["signature"] = sk.sign(envelope.signing_string(e).encode()).hex()
    return e


def test_health(repo): assert client(repo).get("/healthz").json()["status"] == "ok"


def test_risk_shape_and_provenance(repo):
    j = client(repo).get("/v1/risk", params={"lat": LAT, "lon": LON}).json()
    assert j["state"] in ("SAFE", "WATCH", "WARNING", "EVACUATE")
    assert j["data_provenance"] == "synthetic_reconstruction" and j["confidence"] != "high"
    assert {"model_version", "generated_at", "data_cutoff", "confidence"} <= j.keys()      # FR-15


def test_stale_forecast_not_live(repo):
    j = client(repo, NOW + timedelta(hours=3)).get("/v1/risk", params={"lat": LAT, "lon": LON}).json()
    assert j["live"] is False and j["confidence"] == "low"


def test_no_station_in_range_is_404_not_a_guess(repo):
    assert client(repo).get("/v1/risk", params={"lat": 12.9, "lon": 77.6}).status_code == 404


def test_sos_valid_duplicate_tampered(repo):
    c, sk = client(repo), Ed25519PrivateKey.generate()
    e = signed(sk)
    assert c.post("/v1/sos", json=e).json()["status"] == "accepted"
    assert c.post("/v1/sos", json=e).json()["status"] == "duplicate"
    bad = {**signed(sk, "m2"), "lat_e4": 1}
    assert c.post("/v1/sos", json=bad).status_code == 422
    assert c.get("/v1/sos/status", params={"ids": "m1,m2"}).json() == {"m1": "received"}


def test_peer_sync_dedup(repo):
    c, sk = client(repo), Ed25519PrivateKey.generate()
    e = signed(sk, "m3")
    r = c.post("/v1/peer/sync", json={"messages": [e, e]}).json()
    assert [x["status"] for x in r["results"]] == ["accepted", "duplicate"]


def test_responder_requires_token_and_fails_closed(repo):
    assert client(repo).get("/v1/responder/sos").status_code == 401
    assert client(repo, token="").get("/v1/responder/sos", headers={"Authorization": "Bearer "}).status_code == 503
    assert client(repo).get("/v1/responder/sos", headers={"Authorization": "Bearer " + "t" * 32}).status_code == 200


def test_source_health_replay_and_extent_honesty(repo):
    c = client(repo)
    assert c.get("/v1/source-health").json()[0]["source"] == "fixture_synthetic"
    j = c.get("/v1/replay/sep2024-synthetic").json()
    assert j["synthetic"] is True and "SYNTHETIC" in j["notice"]
    assert c.get("/v1/flood-extent").json()["available"] is False


def test_peer_sync_routes_reports_away_from_sos_table(repo):
    c, sk = client(repo), Ed25519PrivateKey.generate()
    e = signed(sk, "r1")
    e.update(message_type="REPORT", payload_b64=base64.b64encode(json.dumps({"type": "blocked_road", "note": "bridge"}).encode()).decode())
    e["signature"] = sk.sign(envelope.signing_string(e).encode()).hex()
    assert c.post("/v1/peer/sync", json={"messages": [e]}).json()["results"][0]["status"] == "accepted"
    assert "r1" not in repo.sos and "r1" in repo.reports


def test_weak_responder_token_fails_closed(repo):
    assert client(repo, token="short").get("/v1/responder/sos", headers={"Authorization": "Bearer short"}).status_code == 503


def test_responder_lockout_after_repeated_failures(repo):
    c = client(repo)
    codes = [c.get("/v1/responder/sos", headers={"Authorization": "Bearer wrong"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    assert c.get("/v1/responder/sos", headers={"Authorization": "Bearer " + "t" * 32}).status_code == 429   # locked even for the right token


def test_non_ascii_token_does_not_500(repo):
    assert client(repo).get("/v1/responder/sos", headers={"Authorization": "Bearer " + "é" * 30}).status_code == 401


def test_oversized_body_rejected(repo):
    assert client(repo).post("/v1/sos", content=b"x" * 70000, headers={"content-type": "application/json"}).status_code == 413
