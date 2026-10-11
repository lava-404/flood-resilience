import os, sys, tempfile, unittest, base64, json
from datetime import datetime, timedelta, timezone
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
for p in ("common", "forecast", "ingest"): sys.path.insert(0, os.path.join(ROOT, "services", p))
os.chdir(ROOT)
from floodcommon import envelope, migrate, service
from floodcommon.ports import InMemoryQueue, LocalSnapshotStore
from floodcommon.repo import InMemoryRepo
from floodres.worker import handle_job
from ingest.adapters import CwcAdapter, FixtureAdapter, SourceUnavailable
from ingest.pipeline import run_ingestion
from ingest import local_demo

FIX = "data/fixtures/replay_sep2024_SYNTHETIC.json"
NOW = datetime(2024, 9, 28, 12, tzinfo=timezone.utc)


class Ingest(unittest.TestCase):
    def setUp(self):
        self.repo, self.q, self.snaps = InMemoryRepo(), InMemoryQueue(), LocalSnapshotStore(tempfile.mkdtemp())

    def test_success_writes_snapshot_observations_run_and_one_job(self):
        run = run_ingestion(FixtureAdapter(FIX, as_of=NOW), self.repo, self.snaps, self.q, NOW)
        self.assertEqual(run["status"], "success")
        self.assertTrue(os.path.exists(os.path.join(self.snaps.root, run["snapshot_key"])))
        self.assertGreater(len(self.repo.observations("DEMO-KOSI-01", "river_level")), 20)
        self.assertEqual(len(self.q.messages), 1)
        self.assertTrue(all(o.provenance == "synthetic_reconstruction" for o in self.repo.obs.values()))

    def test_spike_is_kept_but_flagged(self):
        run_ingestion(FixtureAdapter(FIX, as_of=NOW), self.repo, self.snaps, self.q, NOW)
        flags = [o.quality_flag for o in self.repo.observations("DEMO-KOSI-01", "river_level")]
        self.assertIn("implausible_rate", flags)

    def test_unverified_source_reports_unavailable_without_job(self):
        run = run_ingestion(CwcAdapter(), self.repo, self.snaps, self.q, NOW)
        self.assertEqual(run["status"], "source_unavailable")
        self.assertEqual(self.q.messages, [])
        h = service.source_health_view(self.repo.source_health_rows(), NOW)
        self.assertEqual(h[0]["state"], "never_succeeded")

    def test_snapshot_failure_is_not_success_and_stores_nothing(self):
        class Boom:
            def put(self, *a): raise OSError("s3 down")
        run = run_ingestion(FixtureAdapter(FIX, as_of=NOW), self.repo, Boom(), self.q, NOW)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(self.repo.obs, {}); self.assertEqual(self.q.messages, [])

    def test_official_update_alone_triggers_new_job_even_if_river_silent(self):
        a = FixtureAdapter(FIX, as_of=NOW)
        run_ingestion(a, self.repo, self.snaps, self.q, NOW)
        k1 = self.q.drain()[0]["job_key"]
        run_ingestion(a, self.repo, self.snaps, self.q, NOW)               # same data -> same key (idempotent)
        self.assertEqual(self.q.drain()[0]["job_key"], k1)
        run_ingestion(FixtureAdapter(FIX, as_of=NOW + timedelta(hours=1)), self.repo, self.snaps, self.q, NOW)
        self.assertNotEqual(self.q.drain()[0]["job_key"], k1)

    def test_worker_idempotent(self):
        run_ingestion(FixtureAdapter(FIX, as_of=NOW), self.repo, self.snaps, self.q, NOW)
        job = self.q.drain()[0]
        self.assertEqual(handle_job(job, self.repo, NOW), "ok")
        self.assertEqual(handle_job(job, self.repo, NOW), "duplicate")
        self.assertEqual(len(self.repo.risk_history("DEMO-KOSI-01")), 1)

    def test_worker_unknown_station_raises_for_retry_dlq(self):
        with self.assertRaises(LookupError):
            handle_job({"job_key": "x", "station_id": "nope"}, self.repo, NOW)

    def test_source_health_goes_stale_and_failing(self):
        run_ingestion(FixtureAdapter(FIX, as_of=NOW), self.repo, self.snaps, self.q, NOW)
        self.assertEqual(service.source_health_view(self.repo.source_health_rows(), NOW)[0]["state"], "ok")
        self.assertEqual(service.source_health_view(self.repo.source_health_rows(), NOW + timedelta(hours=4))[0]["state"], "stale")
        run_ingestion(FixtureAdapter("missing.json"), self.repo, self.snaps, self.q, NOW + timedelta(hours=5))
        self.assertEqual(service.source_health_view(self.repo.source_health_rows(), NOW + timedelta(hours=5))[0]["state"], "failing")


class EndToEnd(unittest.TestCase):
    def test_local_demo_pipeline_reaches_evacuate_and_marks_outage_not_live(self):
        repo, rows = local_demo.run(step_hours=1)
        states = [r[1] for r in rows]
        self.assertEqual(states[0], "SAFE"); self.assertIn("EVACUATE", states)
        self.assertTrue(any(not live and conf == "low" for _, _, conf, live in rows))   # injected outage hours


class Ops(unittest.TestCase):
    def test_ops_metrics_never_and_ages(self):
        self.assertEqual(service.ops_metrics(InMemoryRepo(), NOW)["forecast_age_minutes"], 9999)
        repo, _ = local_demo.run(step_hours=1, until=NOW)
        m = service.ops_metrics(repo, NOW + timedelta(minutes=30))
        self.assertEqual(m["forecast_age_minutes"], 30)
        self.assertEqual(m["source_age_minutes"]["fixture_synthetic"], 30)

    def test_demo_until_stops_at_clock(self):
        repo, rows = local_demo.run(step_hours=1, until=NOW)
        self.assertEqual(rows[-1][0], NOW)


class Freshen(unittest.TestCase):
    def test_stale_forecast_loses_live_and_confidence_but_keeps_state(self):
        r = {"state": "WARNING", "confidence": "medium", "live": True, "forecast_generated_at": NOW}
        f = service.freshen(r, NOW + timedelta(hours=2))
        self.assertEqual((f["state"], f["live"], f["confidence"]), ("WARNING", False, "low"))
        self.assertFalse(f["expired"])
        self.assertTrue(service.freshen(r, NOW + timedelta(hours=7))["expired"])
        self.assertTrue(service.freshen(r, NOW + timedelta(minutes=10))["live"])


def make_env(sk, now=NOW, ttl_h=24, hop=0, max_hops=5):
    from cryptography.hazmat.primitives import serialization as s
    pub = sk.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw).hex()
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    e = {"protocol_version": 1, "message_id": "m-1", "origin_peer_id": pub, "message_type": "SOS",
         "created_at": iso(now), "expires_at": iso(now + timedelta(hours=ttl_h)), "hop_count": hop, "max_hops": max_hops,
         "lat_e4": 261500, "lon_e4": 859000, "severity": 3,
         "payload_b64": base64.b64encode(json.dumps({"people_count": 3, "medical": True, "note": "छत पर"}).encode()).decode()}
    e["signature"] = sk.sign(envelope.signing_string(e).encode()).hex()
    return e


class Envelope(unittest.TestCase):
    def setUp(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self.sk = Ed25519PrivateKey.generate()

    def test_valid_and_hop_count_not_signed(self):
        e = make_env(self.sk)
        self.assertEqual(envelope.validate(e, NOW), [])
        e["hop_count"] = 3
        self.assertEqual(envelope.validate(e, NOW), [])

    def test_tamper_detected(self):
        e = make_env(self.sk); e["lat_e4"] += 1
        self.assertEqual(envelope.validate(e, NOW), ["bad_signature"])

    def test_expiry_hops_malformed(self):
        self.assertIn("expired", envelope.validate(make_env(self.sk), NOW + timedelta(hours=25)))
        self.assertIn("bad_hops", envelope.validate(make_env(self.sk, hop=6, max_hops=5), NOW))
        self.assertIn("bad_ttl", envelope.validate(make_env(self.sk, ttl_h=100), NOW))
        self.assertEqual(envelope.validate({"x": 1}, NOW), ["malformed"])


class CrossLanguageVector(unittest.TestCase):
    def test_committed_vector_validates_and_signing_string_matches(self):
        with open("data/fixtures/envelope_vector.json") as f: v = json.load(f)
        now = datetime.fromisoformat(v["now"].replace("Z", "+00:00"))
        self.assertEqual(envelope.signing_string(v["envelope"]), v["signing_string"])
        self.assertEqual(envelope.validate(v["envelope"], now), [])


class Migrations(unittest.TestCase):
    def test_discover_and_core_tables_present(self):
        ms = migrate.discover("infra/db/migrations")
        self.assertEqual(ms[0][0], "001")
        sql = ms[0][2]
        for t in ("stations", "observations", "risk_states", "forecasts", "reports", "sos", "shelters", "ingestion_runs", "model_registry"):
            self.assertIn(f"CREATE TABLE {t} ", sql)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS postgis", sql)


if __name__ == "__main__":
    unittest.main()
