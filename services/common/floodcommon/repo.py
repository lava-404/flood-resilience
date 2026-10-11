"""Repository port + in-memory implementation (used by tests/local demo). PgRepo lives in pgrepo.py."""
from dataclasses import asdict
from .util import haversine_km


class InMemoryRepo:
    def __init__(self):
        self.stations, self.obs, self.risk, self.history = {}, {}, {}, {}
        self.runs, self.reports, self.sos, self.shelters, self.jobs = [], {}, {}, [], {}

    # stations / observations
    def upsert_station(self, st): self.stations[st.id] = st
    def get_station(self, sid): return self.stations.get(sid)
    def list_stations(self): return list(self.stations.values())

    def upsert_observations(self, obs):
        for o in obs:
            self.obs[(o.station_id, o.parameter, o.observed_at)] = o
        return len(obs)

    def observations(self, station_id, parameter, until=None):
        rows = [o for (s, p, _), o in self.obs.items() if s == station_id and p == parameter
                and (until is None or o.observed_at <= until)]
        return sorted(rows, key=lambda o: o.observed_at)

    def nearest_station(self, lat, lon):
        return min(self.stations.values(), key=lambda s: haversine_km(lat, lon, s.lat, s.lon), default=None)

    def stations_nearby(self, lat, lon, radius_km):
        out = [(haversine_km(lat, lon, s.lat, s.lon), s) for s in self.stations.values()]
        return [(round(d, 2), s) for d, s in sorted(out, key=lambda x: x[0]) if d <= radius_km]

    # forecast jobs / risk
    def has_job(self, key): return key in self.jobs

    def save_risk(self, location_id, result, job_key):
        self.jobs[job_key] = "done"
        self.risk[location_id] = result
        self.history.setdefault(location_id, []).append(result)

    def latest_risk(self, location_id): return self.risk.get(location_id)
    def risk_history(self, location_id, limit=48): return self.history.get(location_id, [])[-limit:]

    # ingestion runs / source health
    def record_run(self, run): self.runs.append(dict(run))

    def source_health_rows(self):
        out = {}
        for r in self.runs:
            row = out.setdefault(r["source"], {"source": r["source"], "last_run": None, "last_success": None})
            row["last_run"] = r
            if r["status"] == "success":
                row["last_success"] = r
        return list(out.values())

    # reports / sos / shelters
    def add_report(self, rep):
        if rep["id"] in self.reports: return False
        self.reports[rep["id"]] = rep; return True

    def list_reports(self): return list(self.reports.values())

    def add_sos(self, sos):
        if sos["message_id"] in self.sos: return False
        self.sos[sos["message_id"]] = dict(sos); return True

    def list_sos(self): return list(self.sos.values())
    def sos_states(self, ids): return {i: self.sos[i]["state"] for i in ids if i in self.sos}

    def set_sos_state(self, mid, state):
        if mid not in self.sos: return False
        self.sos[mid]["state"] = state; return True

    def lower_hop_count(self, mid, hop):
        if mid in self.sos: self.sos[mid]["hop_count"] = min(self.sos[mid]["hop_count"], hop)

    def has_message(self, mid): return mid in self.sos or mid in self.reports

    def count_by_peer(self, peer_id, since):
        return (sum(1 for s in self.sos.values() if s["origin_peer_id"] == peer_id and s["received_at"] >= since) +
                sum(1 for r in self.reports.values() if r["reporter_id"] == peer_id and r["received_at"] >= since))

    def add_shelters(self, shelters): self.shelters.extend(shelters)

    def shelters_nearby(self, lat, lon, radius_km):
        out = [(haversine_km(lat, lon, s["lat"], s["lon"]), s) for s in self.shelters]
        return [{**s, "distance_km": round(d, 2)} for d, s in sorted(out, key=lambda x: x[0]) if d <= radius_km]
