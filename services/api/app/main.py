"""FastAPI wiring (SRS 13.3). Endpoint logic lives in floodcommon.api_logic (tested over real HTTP via scripts/dev_server.py).
THIS FILE (routing, validation, middleware, CORS) is UNTESTED in the authoring environment: FastAPI was not installable there."""
import logging
from typing import Annotated, Any
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from floodcommon import api_logic as L
from floodcommon.config import Settings

log = logging.getLogger("floodres.api")
LatQ = Annotated[float, Query(ge=-90, le=90)]
LonQ = Annotated[float, Query(ge=-180, le=180)]


class ReportIn(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    reporter_id: str = Field(max_length=64)
    type: str = Field(max_length=32)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    value: float | None = None
    note: str | None = Field(default=None, max_length=280)


def create_app(repo, settings: Settings | None = None, now_fn=None) -> FastAPI:
    st = settings or Settings()
    now = now_fn or st.clock()
    app = FastAPI(title="FloodResilience API", version="1")
    auth = L.ResponderAuth(st.responder_token)
    if st.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=st.cors_origins, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

    def run(fn, *a, **k):
        try: return fn(*a, **k)
        except L.ApiError as e: raise HTTPException(e.status, e.detail)

    def responder(request: Request):
        run(auth.check, {k.lower(): v for k, v in request.headers.items()}, request.client.host if request.client else "?")

    @app.middleware("http")
    async def limit_body(request: Request, call_next):                      # chunked bodies are not covered: add an edge/WAF limit too
        n = request.headers.get("content-length")
        if n and n.isdigit() and int(n) > L.MAX_BODY_BYTES: return JSONResponse({"detail": "request too large"}, status_code=413)
        return await call_next(request)

    @app.get("/healthz")
    def healthz(): return {"status": "ok", "demo_clock": bool(st.demo_now)}

    @app.get("/readyz")
    def readyz():
        try: ok = repo.ping() if hasattr(repo, "ping") else True
        except Exception: ok = False
        if not ok: raise HTTPException(503, "database unavailable")
        return {"status": "ready"}

    @app.get("/v1/risk")
    def risk(lat: LatQ, lon: LonQ): return run(L.risk, repo, st, now(), lat, lon)

    @app.get("/v1/risk/timeline")
    def timeline(lat: LatQ, lon: LonQ, hours: int = Query(24, ge=1, le=72)): return run(L.timeline, repo, st, now(), lat, lon, hours)

    @app.get("/v1/stations/nearby")
    def stations(lat: LatQ, lon: LonQ, radius_km: float = Query(50, le=200)): return run(L.stations_nearby, repo, lat, lon, radius_km)

    @app.get("/v1/flood-extent")
    def flood_extent(): return L.flood_extent()

    @app.get("/v1/shelters/nearby")
    def shelters(lat: LatQ, lon: LonQ, radius_km: float = Query(25, le=100)): return run(L.shelters, repo, lat, lon, radius_km)

    @app.post("/v1/reports", status_code=201)
    def post_report(r: ReportIn): return run(L.post_report, repo, now(), r.model_dump())

    @app.get("/v1/reports/nearby")
    def reports_nearby(lat: LatQ, lon: LonQ, radius_km: float = Query(25, le=100)): return run(L.reports_nearby, repo, now(), lat, lon, radius_km)

    @app.post("/v1/sos")
    def post_sos(e: dict[str, Any]): return run(L.post_sos, repo, st, now(), e)

    @app.post("/v1/peer/sync")
    def peer_sync(body: dict[str, Any]): return run(L.peer_sync, repo, st, now(), body)

    @app.get("/v1/sos/status")
    def sos_status(ids: str = Query(max_length=4000)): return L.sos_status(repo, ids)

    @app.get("/v1/source-health")
    def source_health(): return L.source_health(repo, now())

    @app.get("/v1/replay/{event_id}")
    def replay(event_id: str, step_hours: int = Query(3, ge=1, le=12)): return run(L.replay, event_id, step_hours)

    @app.get("/v1/responder/sos", dependencies=[Depends(responder)])
    def responder_sos(): return L.responder_sos(repo)

    @app.post("/v1/responder/sos/{mid}/ack", dependencies=[Depends(responder)])
    def ack(mid: str): return run(L.ack, repo, mid)

    @app.get("/v1/responder/overview", dependencies=[Depends(responder)])
    def overview(): return L.overview(repo, st, now())

    return app
