import base64, json, os, sys, unittest
from datetime import datetime, timedelta, timezone
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
for p in ("common", "forecast", "ingest"): sys.path.insert(0, os.path.join(ROOT, "services", p))
os.chdir(ROOT)
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from floodcommon import envelope, migrate, policy, security
from floodcommon.repo import InMemoryRepo

NOW = datetime(2024, 9, 28, 12, tzinfo=timezone.utc)


def make(sk, mid="m", mtype="SOS", payload=None, now=NOW, ttl_h=24, hop=0):
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = payload if payload is not None else ({"people_count": 2, "medical": False} if mtype == "SOS" else {"type": "blocked_road"})
    e = {"protocol_version": 1, "message_id": mid, "origin_peer_id": sk.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw).hex(),
         "message_type": mtype, "created_at": iso(now), "expires_at": iso(now + timedelta(hours=ttl_h)), "hop_count": hop, "max_hops": 5,
         "lat_e4": 261500, "lon_e4": 859000, "severity": 2,
         "payload_b64": base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()}
    e["signature"] = sk.sign(envelope.signing_string(e).encode()).hex()
    return e


class PayloadSchema(unittest.TestCase):
    def test_rejects_bad_payloads_even_when_validly_signed(self):
        sk = Ed25519PrivateKey.generate()
        for bad in ({"people_count": -1}, {"people_count": 501}, {"people_count": "3"}, {"medical": 1}, {"note": "x" * 141}, {"evil": 1}, [1]):
            self.assertEqual(envelope.validate(make(sk, payload=bad), NOW), ["bad_payload"], bad)
        self.assertEqual(envelope.validate(make(sk, payload={"people_count": 3, "medical": True, "note": "छत"}), NOW), [])
        self.assertEqual(envelope.validate(make(sk, mtype="REPORT", payload={"type": "nope"}), NOW), ["bad_payload"])
        e = make(sk); e["payload_b64"] = "!!!"
        self.assertIn("malformed", envelope.validate(e, NOW))    # not base64 -> malformed before schema check


class AcceptPolicy(unittest.TestCase):
    def setUp(self): self.repo, self.sk = InMemoryRepo(), Ed25519PrivateKey.generate()

    def test_accept_duplicate_and_report_routing(self):
        r = policy.accept_message(self.repo, make(self.sk, "a"), "direct", NOW)
        self.assertEqual(r["status"], "accepted")
        self.assertEqual(policy.accept_message(self.repo, make(self.sk, "a"), "gateway", NOW)["status"], "duplicate")
        self.assertEqual(policy.accept_message(self.repo, make(self.sk, "r", "REPORT"), "gateway", NOW)["status"], "accepted")
        self.assertIn("r", self.repo.reports); self.assertNotIn("r", self.repo.sos)

    def test_replay_of_expired_and_forged_and_tampered(self):
        self.assertIn("expired", policy.accept_message(self.repo, make(self.sk, "old", now=NOW - timedelta(days=2), ttl_h=24), "direct", NOW)["problems"])
        e = make(self.sk, "t"); e["severity"] = 3
        self.assertEqual(policy.accept_message(self.repo, e, "direct", NOW)["problems"], ["bad_signature"])
        other = Ed25519PrivateKey.generate(); f = make(self.sk, "f"); f["origin_peer_id"] = make(other)["origin_peer_id"]   # impersonation
        self.assertEqual(policy.accept_message(self.repo, f, "direct", NOW)["status"], "rejected")
        self.assertEqual(self.repo.sos, {})

    def test_relay_cannot_change_signed_fields_but_hop_count_is_free(self):
        e = make(self.sk, "h"); e["hop_count"] = 4
        self.assertEqual(policy.accept_message(self.repo, e, "gateway", NOW)["status"], "accepted")

    def test_garbage_never_raises(self):
        for g in (None, 1, "x", [], {}, {"message_id": 5}, {"message_id": "x" * 500}):
            self.assertEqual(policy.accept_message(self.repo, g, "direct", NOW)["status"], "rejected")

    def test_per_peer_quota_is_transient_and_duplicates_dont_count(self):
        for i in range(policy.PEER_QUOTA_PER_HOUR):
            self.assertEqual(policy.accept_message(self.repo, make(self.sk, f"q{i}"), "direct", NOW)["status"], "accepted")
        self.assertEqual(policy.accept_message(self.repo, make(self.sk, "q0"), "direct", NOW)["status"], "duplicate")     # dup answered before quota
        over = policy.accept_message(self.repo, make(self.sk, "over"), "direct", NOW)
        self.assertEqual((over["status"], over["problems"]), ("rate_limited", ["peer_quota"]))
        self.assertEqual(policy.accept_message(self.repo, make(self.sk, "later", now=NOW + timedelta(hours=1, minutes=1)), "direct", NOW + timedelta(hours=1, minutes=1))["status"], "accepted")


class Security(unittest.TestCase):
    def test_token_rules(self):
        self.assertFalse(security.token_acceptable("")); self.assertFalse(security.token_acceptable("short"))
        self.assertFalse(security.token_acceptable(" " + "a" * 30)); self.assertTrue(security.token_acceptable("a" * 24))

    def test_constant_time_compare_handles_unicode(self):
        self.assertTrue(security.tokens_equal("a" * 24, "a" * 24)); self.assertFalse(security.tokens_equal("é" * 24, "a" * 24))
        self.assertFalse(security.tokens_equal("", "a" * 24))

    def test_lockout_and_expiry(self):
        t = [0.0]; lim = security.FailureLimiter(3, 60, clock=lambda: t[0])
        for _ in range(3): lim.record_failure("ip")
        self.assertTrue(lim.blocked("ip")); self.assertFalse(lim.blocked("other"))
        t[0] = 61; self.assertFalse(lim.blocked("ip"))
        lim.record_failure("ip"); lim.reset("ip"); self.assertFalse(lim.blocked("ip"))

    def test_client_key_uses_last_forwarded_hop(self):
        self.assertEqual(security.client_key({"x-forwarded-for": "6.6.6.6, 9.9.9.9"}, "alb"), "9.9.9.9")   # spoofed first entry ignored
        self.assertEqual(security.client_key({}, "direct"), "direct")


class Migration002(unittest.TestCase):
    def test_least_privilege_role_has_no_delete_or_ddl(self):
        ms = migrate.discover("infra/db/migrations")
        self.assertEqual([m[0] for m in ms], ["001", "002"])
        sql = ms[1][2]
        self.assertIn("CREATE ROLE floodres_app NOLOGIN", sql)
        grants = [l for l in sql.splitlines() if l.startswith("GRANT")]
        self.assertTrue(grants and not any(w in " ".join(grants) for w in ("DELETE", "ALL PRIVILEGES", "CREATE ", "PASSWORD")))
        self.assertNotIn("PASSWORD", sql.upper().replace("NO PASSWORD", ""))


if __name__ == "__main__":
    unittest.main()


class HopCountAndSettings(unittest.TestCase):
    def test_duplicate_with_lower_hop_count_wins_so_a_forged_high_count_cannot_stop_propagation(self):
        repo, sk = InMemoryRepo(), Ed25519PrivateKey.generate()
        policy.accept_message(repo, make(sk, "h", hop=5), "gateway", NOW)            # malicious relay's copy arrives first (hop_count unsigned)
        self.assertEqual(repo.sos["h"]["hop_count"], 5)
        self.assertEqual(policy.accept_message(repo, make(sk, "h", hop=1), "gateway", NOW)["status"], "duplicate")
        self.assertEqual(repo.sos["h"]["hop_count"], 1)
        policy.accept_message(repo, make(sk, "h", hop=4), "gateway", NOW)             # a later higher count never raises it
        self.assertEqual(repo.sos["h"]["hop_count"], 1)

    def test_settings_read_env_at_instantiation_not_import(self):
        from floodcommon.config import Settings
        old = os.environ.get("RESPONDER_TOKEN")
        try:
            os.environ["RESPONDER_TOKEN"] = "x" * 30; self.assertEqual(Settings().responder_token, "x" * 30)
            os.environ["REQUIRE_SOS_SIGNATURE"] = "0"; self.assertFalse(Settings().require_signature)
            del os.environ["REQUIRE_SOS_SIGNATURE"]; self.assertTrue(Settings().require_signature)
        finally:
            os.environ.pop("REQUIRE_SOS_SIGNATURE", None)
            if old is None: os.environ.pop("RESPONDER_TOKEN", None)
            else: os.environ["RESPONDER_TOKEN"] = old
