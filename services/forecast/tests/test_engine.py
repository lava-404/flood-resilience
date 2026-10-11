import os, sys, unittest
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from floodres import quality, replay, risk
from floodres.engine import run_forecast

FIX = os.path.join(os.path.dirname(__file__), "../../../data/fixtures/replay_sep2024_SYNTHETIC.json")
TH = {"warning": 6.0, "danger": 7.0}
NOW = datetime(2024, 9, 28, 12, 0, tzinfo=timezone.utc)


def series(vals, end=NOW):
    n = len(vals)
    return [(end - timedelta(hours=n - 1 - i), v) for i, v in enumerate(vals)]


class Quality(unittest.TestCase):
    def test_outlier_and_rate_rejected(self):
        clean, flags = quality.screen_levels(series([3.0, 3.1, 99.0, 3.2]))
        self.assertEqual([r["reason"] for r in flags], ["out_of_range"])
        self.assertEqual(len(clean), 3)
        _, f1 = quality.screen_levels(series([3.0, 3.1, 55.0, 3.2]))  # in range but physically impossible jump
        self.assertEqual([r["reason"] for r in f1], ["implausible_rate"])
        _, f2 = quality.screen_levels(series([3.0, 5.5]))
        self.assertEqual(f2[0]["reason"], "implausible_rate")

    def test_freshness_classes(self):
        self.assertEqual(quality.freshness(None, NOW, "river_level"), "missing")
        self.assertEqual(quality.freshness(NOW - timedelta(minutes=30), NOW, "river_level"), "fresh")
        self.assertEqual(quality.freshness(NOW - timedelta(hours=2), NOW, "river_level"), "aging")
        self.assertEqual(quality.freshness(NOW - timedelta(hours=5), NOW, "river_level"), "stale")


class Safety(unittest.TestCase):
    rain = series([0.0] * 6)

    def test_official_warning_never_silently_suppressed(self):
        official = {"status": "warning", "observed_at": NOW, "source": "T"}
        out = run_forecast(series([3.0, 3.0, 3.0, 3.0]), self.rain, official, TH, NOW)
        self.assertEqual(out["state"], "WARNING")
        self.assertEqual(out["override"]["code"], "official_floor_applied")
        self.assertTrue(out["conflict"])
        self.assertEqual(out["confidence"], "low")

    def test_stale_river_data_is_not_live_and_low_confidence(self):
        old = series([3.0, 3.1], end=NOW - timedelta(hours=8))
        out = run_forecast(old, self.rain, None, TH, NOW)
        self.assertFalse(out["live"]); self.assertIsNone(out["forecast"])
        self.assertEqual(out["confidence"], "low")
        self.assertEqual(out["state"], "WATCH")  # unknown is not "safe"

    def test_confidence_never_high_without_calibration(self):
        out = run_forecast(series([3.0, 3.0, 3.0, 3.0]), series([0.0] * 6), None, TH, NOW)
        self.assertEqual(out["state"], "SAFE")
        self.assertNotEqual(out["confidence"], "high")
        self.assertEqual(out["interval_method"], "heuristic_uncalibrated")

    def test_aging_river_data_is_never_live(self):
        out = run_forecast(series([3.0, 3.0, 3.0], end=NOW - timedelta(hours=2)), series([0.0] * 6), None, TH, NOW)
        self.assertEqual(out["source_freshness"]["river_level"], "aging")
        self.assertFalse(out["live"])
        fresh = run_forecast(series([3.0, 3.0, 3.0], end=NOW - timedelta(minutes=20)), series([0.0] * 6), None, TH, NOW)
        self.assertTrue(fresh["live"])

    def test_missing_rain_reduces_confidence(self):
        out = run_forecast(series([3.0, 3.0, 3.0, 3.0]), [], None, TH, NOW)
        self.assertIn("rainfall_missing", out["confidence_reasons"])

    def test_rising_to_danger_escalates(self):
        out = run_forecast(series([5.0, 5.4, 5.8, 6.2]), series([10.0] * 6), None, TH, NOW)
        self.assertIn(out["state"], ("WARNING", "EVACUATE"))


class StaleOfficial(unittest.TestCase):
    calm = series([3.0, 3.0, 3.0, 3.0])
    rain = series([0.0] * 6)

    def test_stale_official_warning_still_floors_state_and_is_labelled(self):
        official = {"status": "warning", "observed_at": NOW - timedelta(hours=13), "source": "T"}
        out = run_forecast(self.calm, self.rain, official, TH, NOW)
        self.assertEqual(out["state"], "WARNING")
        self.assertEqual(out["official"]["freshness"], "stale")
        self.assertIn("official_stale_floor_kept", out["confidence_reasons"])
        self.assertNotEqual(out["confidence"], "high")

    def test_stale_official_with_no_river_data_is_warning_not_watch(self):
        official = {"status": "warning", "observed_at": NOW - timedelta(hours=13), "source": "T"}
        out = run_forecast(series([3.0, 3.1], end=NOW - timedelta(hours=8)), self.rain, official, TH, NOW)
        self.assertEqual((out["state"], out["live"], out["confidence"]), ("WARNING", False, "low"))

    def test_very_old_official_is_dropped_but_never_silently(self):
        official = {"status": "severe", "observed_at": NOW - timedelta(hours=60), "source": "T"}
        out = run_forecast(self.calm, self.rain, official, TH, NOW)
        self.assertEqual(out["state"], "SAFE")
        self.assertEqual(out["override"]["code"], "official_expired_not_applied")


class Replay(unittest.TestCase):
    def run_it(self):
        return [(t, o) for t, o in replay.replay(replay.load(FIX))]

    def test_deterministic(self):
        a = [(o["state"], o["confidence"], o["forecast"]) for _, o in self.run_it()]
        b = [(o["state"], o["confidence"], o["forecast"]) for _, o in self.run_it()]
        self.assertEqual(a, b)

    def test_progression_and_never_below_official(self):
        runs = self.run_it()
        states = [o["state"] for _, o in runs]
        self.assertEqual(states[0], "SAFE")
        self.assertIn("EVACUATE", states)
        for _, o in runs:
            if o["official"] and o["official"]["freshness"] != "stale":
                floor = risk.OFFICIAL_FLOOR[o["official"]["status"]]
                self.assertGreaterEqual(risk.RANK[o["state"]], risk.RANK[floor])

    def test_injected_spike_flagged_and_outage_degrades(self):
        runs = self.run_it()
        self.assertTrue(any(f["reason"] == "implausible_rate" for _, o in runs for f in o["quality_flags"]))
        outage = [o for t, o in runs if o["source_freshness"]["river_level"] in ("stale", "missing")]
        self.assertTrue(outage and all(o["confidence"] == "low" and not o["live"] for o in outage))
        self.assertTrue(all(o["data_provenance"] == "synthetic_reconstruction" for _, o in runs))


if __name__ == "__main__":
    unittest.main()
