# Implementation status (verified facts only)

Environment of every "VERIFIED" claim: Linux sandbox, Python 3.12 (stdlib + `cryptography`), Node 22. **No** FastAPI, PostgreSQL, Docker, Terraform, Android SDK, npm registry, or AWS access. macOS was never tried.

## VERIFIED: 73 automated tests, all passing (`make test-all`)
| Suite | Tests | What it really exercises |
|---|---|---|
| `services/forecast/tests` | 14 | quality gate, baseline, risk states, official-warning floor (incl. stale feed kept, >48 h dropped *visibly*), aging data never live, deterministic replay |
| `services/tests` | 34 | ingest pipeline, idempotent worker, freshness/expiry, signed envelope + strict payload schema, accept policy (dup / replay / tamper / impersonation / per-peer quota / hop-count lowering), responder-token helpers, settings, migrations text, **static SQL-vs-schema drift check of the PostgreSQL repository** |
| `scripts/tests` | 7 | Android patch script (against SAMPLE templates), **static** RN/Kotlin/manifest/import contract check, **`scripts/e2e_local.py` (31 checks) run over real HTTP sockets against the dev server** |
| `apps/mobile/tests` | 12 | envelope + signatures (incl. Python-signed vector verified in TypeScript), outbox/dedup/expiry/state machine, multi-hop relay in-process, hop-count lowering, sync (offline failure, rate_limited kept pending), offline status wording, en/hi parity |
| `apps/responder-web/tests` | 6 | dashboard view logic: error classes, stale/expired/not-live badges, source problems, synthetic banner, SOS grouping |
Also: `make demo-local`; `make mutation` injects 5 known safety bugs into a throwaway copy and confirms the e2e and/or unit suites fail for each (all 5 caught).

## What those tests do NOT prove
* **Tested through real HTTP, but not with FastAPI and not with PostgreSQL:** endpoint logic (`floodcommon/api_logic.py`) is exercised via `scripts/dev_server.py`, a stdlib stand-in over an in-memory repository. The FastAPI wiring (`services/api/app/main.py`), `PgRepo` and the SQL are **not executed**. The SQL check is *static* (column names, placeholder counts); it cannot show the queries are valid PostgreSQL/PostGIS.
* "SYNTHETIC replay" = fictional station, rain and official statuses. Nothing here is real data.
* Mobile relay tests are in-process simulations, not devices.

## WRITTEN, NEVER EXECUTED (first drafts)
FastAPI wiring + its 13 tests (`services/api/tests`); `PgRepo` + migrations 001-002 on a real database; SQS worker; ingest CLI/`seed_demo` against PostgreSQL; Dockerfile and docker-compose (incl. `seed` service, LocalStack DLQ); **`scripts/e2e_local.py` against the real stack** (`scripts/up_local.sh`); all Terraform (never `validate`d); deploy/run-task scripts; React Native UI/glue; Kotlin Wi-Fi Direct/mDNS module; Next.js `app/page.tsx`; Amplify config.

## NOT IMPLEMENTED
XGBoost/LightGBM model (no real training data); real CWC/DHM/IMERG/GloFAS adapters (they report "unavailable"); SRTM/Sentinel-1/OSM and flood-extent layers; BLE; payload encryption; Android foreground service (relay works only while the app is open); offline map tile packs; push notifications; CAP export; per-user responder identity (Cognito/OIDC); per-source fetch timeouts/backoff; edge rate limiting/WAF.

## NOT DONE (needs your machine / approval)
Docker stack run + `scripts/up_local.sh`; `pytest` on the FastAPI app; Postgres execution of migrations/queries; `next build`; generating the RN project and building the APK; two-phone relay test; `terraform validate/plan`; any AWS deployment. **No AWS resource exists; no `terraform apply` was run.**

## Fixed in M7 (found by reading the seams, then by mutation testing)
* A stale (>12 h) official warning was silently dropped from the risk floor. It now keeps flooring the state, labelled stale, until 48 h, after which it is dropped **with a visible note**.
* `migrate` crashed in compose (it read `DATABASE_URL`; compose provides `DB_*`) and was all-or-nothing across migrations. Now uses the shared DSN and one transaction per migration.
* In demo-clock mode `PgRepo` stored `received_at` with the DB clock and filtered reports with it, which would have broken quotas and hidden demo reports. Both now use the application clock.
* Unsigned `hop_count`: a relay could pre-empt a message with `hop_count = max_hops` and stop its propagation. The lowest value seen now wins (mobile store and backend). It remains advisory: it can still be forged *downward*; TTL + dedup bound propagation.
* `Settings` read the environment at import time; now at instantiation.

## Security posture (reviewed by reading + unit/e2e tests; NOT penetration-tested; do not call this production-secure)
Done: signed messages with strict payload schema, expiry/future/TTL/hop-limit checks, dedup, per-peer quota with transient-vs-permanent rejection, fail-closed weak/unset responder token, constant-time compare, failed-login lockout, body-size cap, no payload/location in logs, secrets via Secrets Manager, private RDS, no credentials in APK/frontend, least-privilege DB role *written* (disabled by default).
Open: public POST endpoints need WAF/edge rate limiting (peer ids are free to mint); `hop_count` unsigned; payloads unencrypted; responder auth is one shared bearer token (no per-user identity or audit trail); in-process lockout is per task; `use_app_db_role=false` by default; Terraform/Docker unvalidated; dependencies unpinned and unaudited; CORS configured but untested with a browser.
