resource "aws_scheduler_schedule" "ingest" {
  name                         = "${local.name}-ingest"
  state                        = var.schedule_state # DISABLED by default
  schedule_expression          = var.ingest_schedule
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.ingest.arn
      launch_type         = "FARGATE"
      task_count          = 1
      network_configuration {
        subnets          = aws_subnet.public[*].id
        security_groups  = [aws_security_group.svc.id]
        assign_public_ip = true
      }
    }
    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 600
    }
  }
}
