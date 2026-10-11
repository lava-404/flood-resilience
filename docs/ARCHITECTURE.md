# Architecture (as built)

```
EventBridge Scheduler --RunTask--> ECS Fargate: ingest  --raw JSON--> S3 raw/
                                         | normalized obs + run status --> RDS PostgreSQL/PostGIS
                                         | job {job_key, station, as_of} --> SQS --(3 receives)--> DLQ
SQS --> ECS Fargate: forecast worker --> engine (quality gate -> baseline -> heuristic bands -> official-warning floor)
                                         --> risk_states / forecasts in RDS
ALB (HTTPS via ACM) --> ECS Fargate: FastAPI --> RDS            Amplify: Next.js responder console --> API
CloudWatch: logs, ForecastAgeMinutes / SourceAgeMinutes / IngestionFailure / ForecastJobFailure, SQS+ALB alarms
Android: RN UI + Kotlin P2P (Wi-Fi Direct / mDNS) + local queue  --(when online)--> /v1/peer/sync
```

Key decisions
* **One pure engine** (`services/forecast/floodres`) used by the worker, the replay endpoint and the tests, so replay = production code path.
* **Job key = newest input of ANY parameter.** Keying on river data alone would let an official-warning update (or a gauge outage) skip re-forecasting (found and fixed during testing).
* **Fail visible:** API `freshen()` marks forecasts older than 90 min not-live/low-confidence and older than 6 h `expired`, without changing the state. Silence alarms (missing metric = breaching).
* **Official floor:** model state is `max(model, official floor)`; the override is returned and shown. `severe` maps to `WARNING` (configurable in `risk.OFFICIAL_FLOOR`; review with domain experts).
* **No NAT gateway:** Fargate in public subnets (public IP, SG admits only the ALB); RDS in private subnets with no route out.
* **Offline path has zero AWS dependency:** SOS is written to the local store first; sync is a separate step.
