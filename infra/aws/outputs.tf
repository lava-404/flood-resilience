output "api_url"          { value = "${local.has_cert ? "https" : "http"}://${aws_lb.api.dns_name}" }
output "ecr_repositories" { value = { for k, r in aws_ecr_repository.svc : k => r.repository_url } }
output "data_bucket"      { value = aws_s3_bucket.data.bucket }
output "forecast_queue_url" { value = aws_sqs_queue.forecast.url }
output "dlq_url"          { value = aws_sqs_queue.dlq.url }
output "cluster"          { value = aws_ecs_cluster.main.name }
output "api_task_family"  { value = aws_ecs_task_definition.api.family }
output "subnets"          { value = join(",", aws_subnet.public[*].id) }
output "service_sg"       { value = aws_security_group.svc.id }
output "responder_token_secret_arn" { value = aws_secretsmanager_secret.responder_token.arn }
output "db_master_secret_arn" { value = aws_db_instance.main.master_user_secret[0].secret_arn }
output "migrate_task_family" { value = aws_ecs_task_definition.migrate.family }
output "db_app_secret_arn" { value = aws_secretsmanager_secret.db_app.arn }
