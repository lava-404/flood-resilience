# Optional. The access token would land in Terraform state; connecting the repo in the Amplify console avoids that.
resource "aws_amplify_app" "dashboard" {
  count        = var.amplify_repository_url == "" ? 0 : 1
  name         = "${local.name}-responder"
  repository   = var.amplify_repository_url
  access_token = var.amplify_access_token
  platform     = "WEB_COMPUTE"
  build_spec   = file("${path.module}/../../apps/responder-web/amplify.yml")
  environment_variables = {
    AMPLIFY_MONOREPO_APP_ROOT = "apps/responder-web"
    NEXT_PUBLIC_API_BASE      = local.has_cert ? "https://${aws_lb.api.dns_name}" : "http://${aws_lb.api.dns_name}"
  }
}
resource "aws_amplify_branch" "main" {
  count       = var.amplify_repository_url == "" ? 0 : 1
  app_id      = aws_amplify_app.dashboard[0].id
  branch_name = "main"
  framework   = "Next.js - SSR"
}
