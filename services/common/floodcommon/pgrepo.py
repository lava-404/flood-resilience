"""PostgreSQL/PostGIS repository. UNTESTED against a live database (psycopg 3). Mirrors InMemoryRepo's interface."""
import json
from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .models import Observation, Station
from .util import to_json

PT = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography"      # (lon, lat)


class PgRepo:
    def __init__(self, dsn): self.dsn = dsn

    def _c(self): return connect(self.dsn, row_factory=dict_row)

    def _q(self, sql, params=(), one=False, write=False):
        with self._c() as c:
            cur = c.execute(sql, params)
            if write: return cur.rowcount
            return (cur.fetchone() if one else cur.fetchall())

    def ping(self): return self._q("SELECT 1 AS ok", one=True)["ok"] == 1

    # stations / observations
    def upsert_station(self, s):
        self._q(f"""INSERT INTO stations(id,source,name,basin,geom,parameter,threshold_warning,threshold_danger,provenance)
                    VALUES (%s,%s,%s,%s,{PT},%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, geom=EXCLUDED.geom,
                      threshold_warning=EXCLUDED.threshold_warning, threshold_danger=EXCLUDED.threshold_danger""",
                (s.id, s.source, s.name, s.basin, s.lon, s.lat, s.parameter, s.threshold_warning, s.threshold_danger, s.provenance), write=True)

    @staticmethod
    def _st(r): return Station(r["id"], r["source"], r["name"], r["basin"], r["lat"], r["lon"], r["parameter"],
                               r["threshold_warning"], r["threshold_danger"], r["provenance"])

    _ST = "SELECT *, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon FROM stations"

    def get_station(self, sid):
        r = self._q(self._ST + " WHERE id=%s", (sid,), one=True)
        return self._st(r) if r else None

    def list_stations(self): return [self._st(r) for r in self._q(self._ST)]

    def nearest_station(self, lat, lon):
        r = self._q(self._ST + f" ORDER BY geom <-> {PT} LIMIT 1", (lon, lat), one=True)
        return self._st(r) if r else None

    def stations_nearby(self, lat, lon, radius_km):
        rows = self._q(f"SELECT *, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon, ST_Distance(geom,{PT})/1000 AS d "
                       f"FROM stations WHERE ST_DWithin(geom,{PT},%s) ORDER BY d", (lon, lat, lon, lat, radius_km * 1000))
        return [(round(r["d"], 2), self._st(r)) for r in rows]

    def upsert_observations(self, obs):
        with self._c() as c, c.cursor() as cur:
            cur.executemany("""INSERT INTO observations(station_id,parameter,observed_at,received_at,value,text_value,unit,quality_flag,source,provenance)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (station_id,parameter,observed_at) DO UPDATE SET value=EXCLUDED.value, text_value=EXCLUDED.text_value,
                  quality_flag=EXCLUDED.quality_flag, received_at=EXCLUDED.received_at""",
                [(o.station_id, o.parameter, o.observed_at, o.received_at, o.value, o.text_value, o.unit, o.quality_flag, o.source, o.provenance) for o in obs])
        return len(obs)

    def observations(self, station_id, parameter, until=None):
        rows = self._q("SELECT * FROM observations WHERE station_id=%s AND parameter=%s AND (%s::timestamptz IS NULL OR observed_at<=%s) ORDER BY observed_at",
                       (station_id, parameter, until, until))
        return [Observation(r["station_id"], r["parameter"], r["observed_at"], r["received_at"], r["source"], r["value"],
                            r["text_value"], r["unit"], r["quality_flag"], r["provenance"]) for r in rows]

    # forecast jobs / risk
    def has_job(self, key): return self._q("SELECT 1 FROM risk_states WHERE job_key=%s", (key,), one=True) is not None

    def save_risk(self, location_id, result, job_key):
        with self._c() as c:
            with c.transaction():
                row = c.execute("""INSERT INTO risk_states(location_id,job_key,forecast_generated_at,data_cutoff,model_version,state,confidence,live,result)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (job_key) DO NOTHING RETURNING id""",
                    (location_id, job_key, result["forecast_generated_at"], result.get("data_cutoff"), result["model_version"],
                     result["state"], result["confidence"], result["live"], Jsonb(json.loads(to_json(result))))).fetchone()
                if row and result.get("forecast"):
                    for h, v in result["forecast"].items():
                        c.execute("INSERT INTO forecasts(risk_state_id,location_id,horizon_h,q10,q50,q90) VALUES (%s,%s,%s,%s,%s,%s)",
                                  (row["id"], location_id, int(h.rstrip("h")), v["q10"], v["q50"], v["q90"]))

    def latest_risk(self, location_id):
        r = self._q("SELECT result, forecast_generated_at, data_cutoff FROM risk_states WHERE location_id=%s ORDER BY forecast_generated_at DESC LIMIT 1",
                    (location_id,), one=True)
        return {**r["result"], "forecast_generated_at": r["forecast_generated_at"], "data_cutoff": r["data_cutoff"]} if r else None

    def risk_history(self, location_id, limit=48):
        rows = self._q("SELECT result, forecast_generated_at FROM risk_states WHERE location_id=%s ORDER BY forecast_generated_at DESC LIMIT %s", (location_id, limit))
        return [{**r["result"], "forecast_generated_at": r["forecast_generated_at"]} for r in reversed(rows)]

    # runs / health
    def record_run(self, run):
        self._q("""INSERT INTO ingestion_runs(run_id,source,started_at,finished_at,status,records,last_observed_at,snapshot_key,error)
                   VALUES (%(run_id)s,%(source)s,%(started_at)s,%(finished_at)s,%(status)s,%(records)s,%(last_observed_at)s,%(snapshot_key)s,%(error)s)
                   ON CONFLICT (run_id) DO UPDATE SET finished_at=EXCLUDED.finished_at,status=EXCLUDED.status,records=EXCLUDED.records,
                     last_observed_at=EXCLUDED.last_observed_at,snapshot_key=EXCLUDED.snapshot_key,error=EXCLUDED.error""",
                {"snapshot_key": None, **run}, write=True)

    def source_health_rows(self):
        last = {r["source"]: r for r in self._q("SELECT DISTINCT ON (source) * FROM ingestion_runs ORDER BY source, finished_at DESC")}
        ok = {r["source"]: r for r in self._q("SELECT DISTINCT ON (source) * FROM ingestion_runs WHERE status='success' ORDER BY source, finished_at DESC")}
        return [{"source": s, "last_run": last[s], "last_success": ok.get(s)} for s in last]

    # reports / sos / shelters
    def add_report(self, r):
        return self._q(f"""INSERT INTO reports(id,reporter_id,type,geom,value,note,created_at,expires_at,verification_state)
                           VALUES (%s,%s,%s,{PT},%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                       (r["id"], r["reporter_id"], r["type"], r["lon"], r["lat"], r.get("value"), r.get("note"),
                        r["created_at"], r["expires_at"], r["verification_state"]), write=True) == 1

    def list_reports(self):
        return self._q("SELECT *, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon FROM reports WHERE expires_at > now() ORDER BY created_at DESC LIMIT 500")

    def add_sos(self, s):
        return self._q(f"""INSERT INTO sos(message_id,origin_peer_id,geom,people_count,medical_flag,severity,created_at,expires_at,hop_count,received_via,state,envelope)
                           VALUES (%s,%s,{PT},%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (message_id) DO NOTHING""",
                       (s["message_id"], s["origin_peer_id"], s["lon"], s["lat"], s.get("people_count"), s["medical_flag"], s["severity"],
                        s["created_at"], s["expires_at"], s["hop_count"], s["received_via"], s["state"], Jsonb(s["envelope"])), write=True) == 1

    def list_sos(self):
        return self._q("SELECT *, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon FROM sos ORDER BY created_at DESC LIMIT 1000")

    def sos_states(self, ids):
        return {r["message_id"]: r["state"] for r in self._q("SELECT message_id,state FROM sos WHERE message_id = ANY(%s)", (list(ids),))}

    def set_sos_state(self, mid, state):
        return self._q("UPDATE sos SET state=%s WHERE message_id=%s", (state, mid), write=True) == 1
        
    def lower_hop_count(self, mid, hop):
        self._q(
            "UPDATE sos SET hop_count = LEAST(hop_count, %s) "
            "WHERE message_id = %s",
            (hop, mid),
            write=True,
        )

    def has_message(self, mid):
        return self._q("SELECT 1 FROM sos WHERE message_id=%s UNION ALL SELECT 1 FROM reports WHERE id=%s", (mid, mid), one=True) is not None

    def count_by_peer(self, peer_id, since):
        r = self._q("SELECT (SELECT count(*) FROM sos WHERE origin_peer_id=%s AND received_at>=%s) + "
                    "(SELECT count(*) FROM reports WHERE reporter_id=%s AND received_at>=%s) AS n", (peer_id, since, peer_id, since), one=True)
        return r["n"]

    def add_shelters(self, shelters):
        for s in shelters:
            self._q(f"INSERT INTO shelters(id,name,geom,capacity,availability,provenance) VALUES (%s,%s,{PT},%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                    (s["id"], s["name"], s["lon"], s["lat"], s.get("capacity"), s.get("availability"), s.get("provenance", "observed")), write=True)

    def shelters_nearby(self, lat, lon, radius_km):
        rows = self._q(f"SELECT id,name,capacity,availability,provenance,ST_Y(geom::geometry) AS lat,ST_X(geom::geometry) AS lon,"
                       f"ST_Distance(geom,{PT})/1000 AS d FROM shelters WHERE ST_DWithin(geom,{PT},%s) ORDER BY d",
                       (lon, lat, lon, lat, radius_km * 1000))
        return [{**{k: v for k, v in r.items() if k != "d"}, "distance_km": round(r["d"], 2)} for r in rows]
