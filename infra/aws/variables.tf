variable "project"     { default = "floodres" }
variable "environment" { default = "demo" }
variable "region"      { default = "ap-south-1" }

variable "budget_email" {
  type        = string
  description = "Receives AWS Budgets + CloudWatch alarm email (alarm subscription needs a confirmation click)."
}
variable "monthly_budget_usd" { default = 50 }

variable "image_tag" {
  type        = string
  description = "Immutable image tag (git short SHA) already pushed to ECR by scripts/deploy.sh."
}

variable "acm_certificate_arn" {
  type        = string
  default     = ""
  description = "ACM cert (same region) for a domain you control. If empty, the ALB is plain HTTP and allow_insecure_http_demo must be true."
}
variable "allow_insecure_http_demo" {
  type        = bool
  default     = false
  description = "Explicit opt-in to an HTTP-only ALB. NEVER send real SOS/location data over it."
}

variable "db_instance_class"        { default = "db.t4g.micro" }
variable "db_engine_version"        { default = "16" }
variable "db_allocated_storage"     { default = 20 }
variable "protect_data" {
  type        = bool
  default     = true
  description = "RDS deletion protection + final snapshot. Set false only after you confirmed what to retain."
}

variable "api_cpu"      { default = 256 }
variable "api_memory"   { default = 512 }
variable "forecast_desired_count" { default = 1 }

variable "ingest_adapter"  { default = "fixture" }
variable "ingest_schedule" { default = "rate(30 minutes)" }
variable "schedule_state" {
  default     = "DISABLED"
  description = "Scheduler starts DISABLED so nothing runs (or bills) until you enable it deliberately."
  validation {
    condition     = contains(["ENABLED", "DISABLED"], var.schedule_state)
    error_message = "ENABLED or DISABLED."
  }
}

variable "demo_now"          { default = "" }  # e.g. 2024-09-28T20:00:00+00:00 pins API/ingest clocks to the SYNTHETIC replay
variable "dashboard_origin"  { default = "" }  # Amplify URL for CORS, e.g. https://main.xxxx.amplifyapp.com

variable "amplify_repository_url" { default = "" }
variable "amplify_access_token" {
  default   = ""
  sensitive = true # NOTE: ends up in Terraform state. Prefer connecting the repo in the Amplify console.
}

variable "use_app_db_role" {
  type        = bool
  default     = false
  description = "After running docs/DEPLOYMENT.md 'least-privilege DB user', set true so api/ingest/forecast stop using the RDS master user."
}
variable "db_app_user" { default = "floodres_svc" }
