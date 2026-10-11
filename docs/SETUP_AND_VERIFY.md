# Setup & verification (run these; nothing below was run by the author unless marked VERIFIED)

## Level 1: no installs (Python 3.12 stdlib + `cryptography`, Node >= 22.6). VERIFIED by the author.
```bash
make test-all        # 73 tests: forecast 14, backend 34, scripts 7, mobile 12, dashboard logic 6
make mutation        # proves the safety tests can fail (injects 5 bugs into a temp copy)
make demo-local      # ingest -> queue -> forecast worker over the SYNTHETIC replay, in memory
```
Expected: all pass (VERIFIED on Linux/Python 3.12/Node 22; macOS not tried); the demo prints SAFE -> WATCH -> WARNING -> EVACUATE.

## Level 1.5: dependency-free dev server + dashboard/mobile against it (no Docker, no pip). VERIFIED only via `make e2e-dev`.
```bash
RESPONDER_TOKEN=local-responder-token-0123456789 python3 scripts/dev_server.py --port 8000   # SYNTHETIC data, in-memory, dev only
API_URL=http://localhost:8000 python3 scripts/e2e_local.py                                  # 31 checks (needs `cryptography`)
```

## Level 2: API without Docker/DB (needs network for pip). NOT run by the author.
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r services/requirements.txt -r services/requirements-dev.txt
export PYTHONPATH=services/common:services/forecast:services/ingest:services/api
pytest services/api/tests -q                                   # 13 API tests
REPO=memory RESPONDER_TOKEN=local-responder-token-0123456789 uvicorn app.asgi:app --port 8000 &   # seeded synthetic demo
API_URL=http://localhost:8000 scripts/smoke_test.sh            # expect: SMOKE PASSED
curl -s "localhost:8000/v1/replay/sep2024-synthetic?step_hours=6" | head -c 600
```

## Level 3: full local stack (Docker). NOT run by the author. One command, then the end-to-end test against the REAL API + PostgreSQL/PostGIS + SQS worker:
```bash
scripts/up_local.sh      # compose up (db, localstack, migrate, api, forecast, seed) -> scripts/e2e_local.py; prints logs on failure
```
Manual steps:
```bash
docker compose up --build -d db localstack localstack-init migrate api forecast
docker compose run --rm --entrypoint python api -m ingest.seed_demo        # synthetic replay into PostGIS
API_URL=http://localhost:8000 scripts/smoke_test.sh
# SQS path: ingest publishes a job, forecast worker consumes it
docker compose run --rm ingest && docker compose logs forecast | tail
# DLQ acceptance test: a poison job must retry 3x then land in the DLQ
docker compose exec localstack awslocal sqs send-message --queue-url http://localhost:4566/000000000000/floodres-forecast-jobs \
  --message-body '{"job_key":"poison","station_id":"nope"}'
sleep 60; docker compose exec localstack awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/floodres-forecast-jobs-dlq --attribute-names ApproximateNumberOfMessages
```
Responder console: `cd apps/responder-web && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev`, sign in with `local-responder-token-0123456789`.

## Level 4: Android APK. NOT run by the author. Needs JDK 17, Android SDK, Node, network.
```bash
scripts/check_env.sh && scripts/mobile_bootstrap.sh && scripts/build_apk.sh
adb install -r apps/mobile/FloodResilienceApp/android/app/build/outputs/apk/debug/app-debug.apk
```
Debug API access: `adb reverse tcp:8000 tcp:8000`. macOS details/troubleshooting: `docs/MACOS_SETUP.md`. P2P needs two real phones: `docs/DEVICE_TEST.md`.

## Infrastructure checks (no cloud spend)
```bash
cd infra/aws && terraform init -backend=false && terraform validate && terraform fmt -check
```
