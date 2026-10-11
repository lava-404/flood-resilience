"""Generates a SYNTHETIC replay fixture shaped like the late-Sept 2024 Nepal-Bihar event.
NOT real observations: no real gauge, rainfall or CWC/DHM record is used. Station and official
statuses are fictional. Replace with an adapter-fed reconstruction when real data is accessible."""
import json, math
from datetime import datetime, timedelta, timezone

T0 = datetime(2024, 9, 27, 0, 0, tzinfo=timezone.utc)
HOURS = 60
levels, rain, official = [], [], []
for h in range(HOURS):
    t = T0 + timedelta(hours=h)
    lvl = 3.5 + 4.2 / (1 + math.exp(-(h - 30) / 6)) + 0.05 * math.sin(h)
    rn = 25 * math.exp(-((h - 20) / 6) ** 2)
    if not (44 <= h <= 47):                       # injected 4-hour gauge outage
        levels.append({"t": t.isoformat(), "value": round(lvl, 3)})
    rain.append({"t": t.isoformat(), "value": round(rn, 2)})
    status = "normal" if h < 28 else "watch" if h < 34 else "warning" if h < 40 else "severe"
    official.append({"t": t.isoformat(), "status": status})
levels[20]["value"] = 55.0                        # injected spike: must be rejected as an outlier
json.dump({"synthetic": True, "provenance": "synthetic_reconstruction",
           "note": "Fictional station DEMO-KOSI-01. Not real data.", "station": "DEMO-KOSI-01",
           "thresholds": {"warning": 6.0, "danger": 7.0, "unit": "m"},
           "levels": levels, "rain": rain, "official": official, "official_source": "DEMO_OFFICIAL"},
          open("data/fixtures/replay_sep2024_SYNTHETIC.json", "w"), indent=1)
print("wrote", len(levels), "level records")
