resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "disabled" # cost: enable only while debugging
  }
}

resource "aws_cloudwatch_log_group" "svc" {
  for_each          = toset(["api", "ingest", "forecast"])
  name              = "/${var.project}/${var.environment}/${each.key}"
  retention_in_days = 14
}

locals {
  img = { for k, r in aws_ecr_repository.svc : k => "${r.repository_url}:${var.image_tag}" }
  db_env = [
    { name = "DB_HOST", value = aws_db_instance.main.address },
    { name = "DB_NAME", value = "floodres" },
    { name = "DB_USER", value = var.use_app_db_role ? var.db_app_user : "floodres" },
    { name = "DB_SSLMODE", value = "require" },
    { name = "AWS_DEFAULT_REGION", value = var.region },
    { name = "DEMO_NOW", value = var.demo_now },
    { name = "REPLAY_MODE", value = var.demo_now == "" ? "0" : "1" },
  ]
  db_secret = {
    name      = "DB_PASSWORD"
    valueFrom = "${var.use_app_db_role ? aws_secretsmanager_secret.db_app.arn : aws_db_instance.main.master_user_secret[0].secret_arn}:password::"
  }
  master_secret = { name = "DB_PASSWORD", valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::" }
}

# A DB_PASSWORD env var sourced from Secrets Manager is injected at task start; nothing is baked into images.
resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.api.arn
  container_definitions = jsonencode([{
    name = "api", image = local.img.api, essential = true,
    portMappings = [{ containerPort = 8000 }],
    environment  = concat(local.db_env, [{ name = "METRICS_ENABLED", value = "1" }, { name = "CORS_ORIGINS", value = var.dashboard_origin }]),
    secrets      = [local.db_secret, { name = "RESPONDER_TOKEN", valueFrom = aws_secretsmanager_secret.responder_token.arn }],
    healthCheck  = { command = ["CMD-SHELL", "python -c \"import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=2)\""], interval = 30, timeout = 5, retries = 3, startPeriod = 20 },
    logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.svc["api"].name, "awslogs-region" = var.region, "awslogs-stream-prefix" = "api" } }
  }])
}

# Migrations need the owner (master) login; every long-running task can use the restricted role.
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.api.arn
  container_definitions = jsonencode([{
    name = "migrate", image = local.img.api, essential = true, command = ["python", "-m", "floodcommon.migrate"],
    environment = concat([for e in local.db_env : e if e.name != "DB_USER"], [{ name = "DB_USER", value = "floodres" }, { name = "DB_APP_SECRET_ARN", value = aws_secretsmanager_secret.db_app.arn }]),
    secrets     = [local.master_secret],
    logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.svc["api"].name, "awslogs-region" = var.region, "awslogs-stream-prefix" = "migrate" } }
  }])
}

resource "aws_ecs_task_definition" "ingest" {
  family                   = "${local.name}-ingest"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.ingest.arn
  container_definitions = jsonencode([{
    name = "ingest", image = local.img.ingest, essential = true,
    environment = concat(local.db_env, [
      { name = "ADAPTER", value = var.ingest_adapter },
      { name = "SNAPSHOT_BUCKET", value = aws_s3_bucket.data.bucket },
      { name = "FORECAST_QUEUE_URL", value = aws_sqs_queue.forecast.url }]),
    secrets = [local.db_secret],
    logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.svc["ingest"].name, "awslogs-region" = var.region, "awslogs-stream-prefix" = "ingest" } }
  }])
}

resource "aws_ecs_task_definition" "forecast" {
  family                   = "${local.name}-forecast"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.forecast.arn
  container_definitions = jsonencode([{
    name = "forecast", image = local.img.forecast, essential = true,
    environment = concat(local.db_env, [{ name = "FORECAST_QUEUE_URL", value = aws_sqs_queue.forecast.url }, { name = "METRICS_ENABLED", value = "1" }]),
    secrets = [local.db_secret],
    logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.svc["forecast"].name, "awslogs-region" = var.region, "awslogs-stream-prefix" = "forecast" } }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.svc.id]
    assign_public_ip = true # no NAT (cost); SG admits only the ALB
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  depends_on = [aws_lb_listener.https, aws_lb_listener.http_forward, aws_lb_listener.http_redirect]
}

resource "aws_ecs_service" "forecast" {
  name            = "forecast"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.forecast.arn
  desired_count   = var.forecast_desired_count
  launch_type     = "FARGATE"
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.svc.id]
    assign_public_ip = true
  }
}
