"""Replaceable source adapters (SRS 9). Only the fixture adapter is functional. Real-source adapters are
deliberately NOT implemented because no machine-readable endpoint has been verified (SRS: never assume a website is an API)."""
import json
from dataclasses import dataclass
from datetime import datetime
from floodcommon.models import Observation, Station


class SourceUnavailable(Exception): pass


@dataclass
class RawSnapshot:
    source: str
    fetched_at: datetime
    content_type: str
    body: bytes


class FixtureAdapter:
    """Replays the SYNTHETIC fixture up to `as_of` (so the demo behaves like a live feed). Not real data."""
    name = "fixture_synthetic"

    def __init__(self, path, as_of: datetime | None = None):
        self.path, self.as_of = path, as_of

    def fetch(self, now):
        with open(self.path) as f:
            d = json.load(f)
        cut = (self.as_of or now).isoformat()
        for k in ("levels", "rain", "official"):
            d[k] = [r for r in d[k] if r["t"] <= cut]
        return RawSnapshot(self.name, now, "application/json", json.dumps(d).encode())

    def normalize(self, raw, received_at):
        d = json.loads(raw.body)
        prov = d["provenance"]                       # 'synthetic_reconstruction'
        sid, th = d["station"], d["thresholds"]
        st = Station(sid, self.name, "Demo station (fictional)", "Kosi (demo)", 26.15, 85.90, "river_level",
                     th["warning"], th["danger"], prov)
        t = datetime.fromisoformat
        obs = [Observation(sid, "river_level", t(r["t"]), received_at, self.name, value=r["value"], unit="m", provenance=prov) for r in d["levels"]]
        obs += [Observation(sid, "rainfall", t(r["t"]), received_at, self.name, value=r["value"], unit="mm/h", provenance=prov) for r in d["rain"]]
        obs += [Observation(sid, "official_status", t(r["t"]), received_at, d["official_source"], text_value=r["status"], provenance=prov) for r in d["official"]]
        return [st], obs


class UnverifiedSourceAdapter:
    """Placeholder for sources whose machine-readable access is unverified. Always reports unavailable."""
    name, note = "unverified", ""

    def __init__(self, *a, **k): pass
    def fetch(self, now): raise SourceUnavailable(f"{self.name}: {self.note}")
    def normalize(self, raw, received_at): raise NotImplementedError


class CwcAdapter(UnverifiedSourceAdapter):
    name, note = "cwc", "no verified machine-readable CWC endpoint; obtain an approved feed/dataset, then implement fetch()/normalize()"

class DhmAdapter(UnverifiedSourceAdapter):
    name, note = "dhm", "DHM real-time page is a web page, not a verified API; use downloadable bulletins or a data agreement"

class ImergAdapter(UnverifiedSourceAdapter):
    name, note = "gpm_imerg", "needs NASA Earthdata credentials (Secrets Manager) and a gridded-rain extraction step; not implemented"

class GlofasAdapter(UnverifiedSourceAdapter):
    name, note = "glofas", "needs Copernicus CDS/EWDS credentials and terms review; not implemented"


REGISTRY = {"fixture": FixtureAdapter, "cwc": CwcAdapter, "dhm": DhmAdapter, "imerg": ImergAdapter, "glofas": GlofasAdapter}
