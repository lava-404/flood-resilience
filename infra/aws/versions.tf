# UNVALIDATED: written without Terraform available. Run `terraform init -backend=false && terraform validate` first.
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = var.project, Environment = var.environment, ManagedBy = "terraform", Purpose = "hackathon-demo" }
  }
}

data "aws_caller_identity" "me" {}
data "aws_availability_zones" "az" { state = "available" }

locals {
  name = "${var.project}-${var.environment}"
  azs  = slice(data.aws_availability_zones.az.names, 0, 2)
}
