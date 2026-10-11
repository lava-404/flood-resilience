#!/usr/bin/env python3
"""DEV-ONLY, dependency-free API server (standard library) over the SAME endpoint logic as the FastAPI app, with an in-memory
repository seeded from the SYNTHETIC replay. For trying the dashboard/mobile app without Docker or pip, and for testing
scripts/e2e_local.py here. NOT for deployment: single process, no TLS, no persistence, not the FastAPI wiring, no PostgreSQL.
    RESPONDER_TOKEN=local-responder-token-0123456789 python3 scripts/dev_server.py --port 8000"""
import argparse, json, os, re, sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in ("common", "forecast", "ingest"): sys.path.insert(0, os.path.join(ROOT, "services", p))
from floodcommon import api_logic as L
from floodcommon.config import Settings
from floodcommon.util import to_json


def build(settings=None, repo=None):
    st = settings or Settings()
    st.demo_now = st.demo_now or "2024-09-28T20:00:00+00:00"            # always inside the SYNTHETIC replay
    if repo is None:
        from ingest import local_demo
        repo, _ = local_demo.run(step_hours=1, until=datetime.fromisoformat(st.demo_now)); local_demo.seed_shelters(repo)
    return st, repo


def make_handler(st, repo):
    clock, auth = st.clock(), L.ResponderAuth(st.responder_token)
    G = lambda q, k, d=None: q.get(k, [d])[0]

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *a): pass

        def _send(self, status, body):
            data = to_json(body).encode()
            self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data)))
            origin = self.headers.get("Origin")
            if origin and origin in st.cors_origins: self.send_header("Access-Control-Allow-Origin", origin); self.send_header("Vary", "Origin")
            self.end_headers(); self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204); origin = self.headers.get("Origin")
            if origin and origin in st.cors_origins:
                for k, v in (("Access-Control-Allow-Origin", origin), ("Access-Control-Allow-Headers", "Authorization, Content-Type"), ("Access-Control-Allow-Methods", "GET, POST")): self.send_header(k, v)
            self.send_header("Content-Length", "0"); self.end_headers()

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > L.MAX_BODY_BYTES: raise L.ApiError(413, "request too large")
            try: return json.loads(self.rfile.read(n) or b"null")
            except ValueError: raise L.ApiError(422, "invalid JSON")

        def _route(self, method):
            u = urlparse(self.path); q = parse_qs(u.query); p = u.path; hdrs = {k.lower(): v for k, v in self.headers.items()}
            ip, now = self.client_address[0], clock()
            if method == "GET":
                if p == "/healthz": return {"status": "ok", "demo_clock": bool(st.demo_now)}
                if p == "/readyz": return {"status": "ready"}
                if p == "/v1/risk": return L.risk(repo, st, now, G(q, "lat"), G(q, "lon"))
                if p == "/v1/risk/timeline": return L.timeline(repo, st, now, G(q, "lat"), G(q, "lon"), int(G(q, "hours", 24)))
                if p == "/v1/stations/nearby": return L.stations_nearby(repo, G(q, "lat"), G(q, "lon"), G(q, "radius_km", 50))
                if p == "/v1/flood-extent": return L.flood_extent()
                if p == "/v1/shelters/nearby": return L.shelters(repo, G(q, "lat"), G(q, "lon"), G(q, "radius_km", 25))
                if p == "/v1/reports/nearby": return L.reports_nearby(repo, now, G(q, "lat"), G(q, "lon"), G(q, "radius_km", 25))
                if p == "/v1/sos/status": return L.sos_status(repo, G(q, "ids", ""))
                if p == "/v1/source-health": return L.source_health(repo, now)
                m = re.fullmatch(r"/v1/replay/([\w-]+)", p)
                if m: return L.replay(m.group(1), int(G(q, "step_hours", 3)))
                if p == "/v1/responder/sos": auth.check(hdrs, ip); return L.responder_sos(repo)
                if p == "/v1/responder/overview": auth.check(hdrs, ip); return L.overview(repo, st, now)
            else:
                if p == "/v1/sos": return L.post_sos(repo, st, now, self._body())
                if p == "/v1/peer/sync": return L.peer_sync(repo, st, now, self._body())
                if p == "/v1/reports": return L.post_report(repo, now, self._body() or {})
                m = re.fullmatch(r"/v1/responder/sos/([\w-]+)/ack", p)
                if m: auth.check(hdrs, ip); return L.ack(repo, m.group(1))
            raise L.ApiError(404, "not found")

        def _handle(self, method):
            try: self._send(200, self._route(method))
            except L.ApiError as e: self._send(e.status, {"detail": e.detail})
            except Exception as e: self._send(500, {"detail": f"{type(e).__name__}"})
        def do_GET(self): self._handle("GET")
        def do_POST(self): self._handle("POST")
    return H


def serve(port=8000, host="127.0.0.1", settings=None, repo=None):
    st, repo = build(settings, repo)
    return ThreadingHTTPServer((host, port), make_handler(st, repo))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8000); ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args(); srv = serve(a.port, a.host)
    print(f"DEV server (SYNTHETIC data, in-memory) on http://{a.host}:{a.port}  clock pinned to {os.getenv('DEMO_NOW') or '2024-09-28T20:00:00+00:00'}"); srv.serve_forever()
