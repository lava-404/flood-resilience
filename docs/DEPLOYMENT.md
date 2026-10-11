# AWS deployment (NOTHING here has been run; every step that creates paid resources needs YOUR explicit go-ahead)

Region default `ap-south-1`. Always-on cost drivers: ALB, RDS instance + storage, two Fargate tasks (API, forecast worker), plus small S3/ECR/CloudWatch/SQS charges. Check the AWS Pricing Calculator for your region; budget alerts below are **notifications, not spending caps**.

0. Prereqs: AWS CLI authenticated via SSO/IAM user **on your machine** (never in the repo/APK), Terraform >= 1.6, Docker. A domain + ACM certificate in the same region (preferred). Without one the plan **fails unless** `allow_insecure_http_demo=true`; never send real SOS/location data over that HTTP endpoint.
1. `cp infra/aws/terraform.tfvars.example infra/aws/terraform.tfvars`, set `budget_email`, leave `image_tag` for step 4.
2. `cd infra/aws && terraform init && terraform validate`
3. **[approval + small cost]** create only the registries and the secret container:
   `terraform apply -target=aws_ecr_repository.svc -target=aws_ecr_lifecycle_policy.svc -target=aws_secretsmanager_secret.responder_token -var image_tag=placeholder`
4. Set the responder token out-of-band: `aws secretsmanager put-secret-value --secret-id $(terraform output -raw responder_token_secret_arn) --secret-string "$(openssl rand -hex 24)"`
5. **[ECR push]** `cd ../.. && CONFIRM=yes scripts/deploy.sh` -> prints the tag; set `image_tag` in `terraform.tfvars`.
6. `terraform -chdir=infra/aws plan -out tfplan` and **read it**.
7. **[approval, recurring cost]** `terraform -chdir=infra/aws apply tfplan`. Confirm the SNS email subscription (check your inbox).
8. `CONFIRM=yes scripts/run_task.sh migrate` (runs migrations 001-002 with the owner login via a dedicated task) (installs PostGIS + schema from inside the VPC). If the API service restarted before the DB existed, it recovers on its own.
8b. **Least-privilege DB user** (do this before real use): `aws secretsmanager put-secret-value --secret-id $(terraform -chdir=infra/aws output -raw db_app_secret_arn) --secret-string "{\"username\":\"floodres_svc\",\"password\":\"$(openssl rand -hex 24)\"}"`, then `CONFIRM=yes scripts/run_task.sh dbuser`, then re-apply with `use_app_db_role=true` (**approval**: restarts services). The role can SELECT/INSERT/UPDATE only: no DELETE, no DDL.
9. Demo data: `terraform apply -var demo_now=2024-09-28T20:00:00+00:00`, then `CONFIRM=yes DEMO_AS_OF=2024-09-28T20:00:00+00:00 scripts/run_task.sh seed`. The API then answers from a pinned clock inside the SYNTHETIC replay and says so (`clock: demo`).
10. `API_URL=$(terraform -chdir=infra/aws output -raw api_url) scripts/smoke_test.sh`
11. Scheduled ingestion stays **DISABLED** until you set `schedule_state=ENABLED`. Real adapters do not exist yet, so enabling it with `ingest_adapter=fixture` only re-ingests synthetic data.
12. Dashboard: connect the repo in Amplify (or set `amplify_repository_url`, noting the token would enter state), build root `apps/responder-web`, set `NEXT_PUBLIC_API_BASE`, then re-apply with `dashboard_origin=<amplify url>` for CORS.
13. Budget/alarm check: AWS console -> Budgets and CloudWatch alarms exist; trigger the DLQ alarm by sending a poison message to the queue.

Known gaps vs SRS: until `use_app_db_role=true` the API/workers use the RDS master user; scheduler tasks have no bounded timeout; responder auth is a shared bearer token (replace with Cognito/OIDC); no VPC endpoints/NAT (tasks use public IPs behind a locked-down SG); no WAF/rate limiting on public POST endpoints; DB-outage read caching not implemented.
