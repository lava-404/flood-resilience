resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier                  = local.name
  engine                      = "postgres"
  engine_version              = var.db_engine_version
  instance_class              = var.db_instance_class
  allocated_storage           = var.db_allocated_storage
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = "floodres"
  username                    = "floodres"
  manage_master_user_password = true # password lives in a Secrets Manager secret AWS creates; never in .tf or state
  db_subnet_group_name        = aws_db_subnet_group.main.name
  vpc_security_group_ids      = [aws_security_group.db.id]
  publicly_accessible         = false
  multi_az                    = false
  backup_retention_period     = 7
  deletion_protection         = var.protect_data
  skip_final_snapshot         = false
  final_snapshot_identifier   = "${local.name}-final"
  auto_minor_version_upgrade  = true
  apply_immediately           = true
}

# Created EMPTY on purpose: set the value out-of-band so it never enters Git or Terraform state:
#   aws secretsmanager put-secret-value --secret-id <responder_token_secret_arn> --secret-string "$(openssl rand -hex 24)"
resource "aws_secretsmanager_secret" "responder_token" {
  name                    = "${local.name}/responder-token"
  recovery_window_in_days = 7
}

# Credentials for the least-privilege login (member of role floodres_app). Created EMPTY; JSON {"username":"...","password":"..."} is set out-of-band.
resource "aws_secretsmanager_secret" "db_app" {
  name                    = "${local.name}/db-app"
  recovery_window_in_days = 7
}
