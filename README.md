# FloodResilience

Android-first flood early warning + offline SOS relay for Nepal-India river basins (Kosi, Gandak, Bagmati). Built against SRS v1.1.
It complements official CWC/DHM warnings; it does not replace them.

> **Read `docs/STATUS.md` first.** Parts are verified by automated tests, parts are first-draft source that has never been run, and some SRS items are not implemented. All demo data is **synthetic**.

```
services/forecast   quality gate, baseline, risk + official-warning rules, replay        (tested)
services/common     models, repositories (memory + PostGIS), envelope, freshness rules   (memory/envelope tested)
services/ingest     source adapters, ingestion pipeline, seed/demo                       (pipeline tested)
services/api        FastAPI service                                                      (untested)
apps/mobile         React Native UI + tested TS core + Kotlin P2P module                 (core tested; rest untested)
apps/responder-web  Next.js console                                                      (untested)
infra/aws           Terraform: VPC, RDS, ECS Fargate, ALB, SQS+DLQ, S3, ECR, Scheduler, CloudWatch, Budgets, Amplify  (unvalidated)
infra/db            PostGIS migrations
data/fixtures       SYNTHETIC replay, demo shelters, envelope test vector
docs/               status, setup, deployment, cleanup, architecture, data sources, ML, offline networking, demo script
```

Try it now (no installs): `make test-all && make demo-local`. Everything else: `docs/SETUP_AND_VERIFY.md`.
Deploying to AWS costs money and is never automatic: `docs/DEPLOYMENT.md`. Credentials never belong in the APK, frontend or repo.
