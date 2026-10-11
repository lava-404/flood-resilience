#!/usr/bin/env bash
# Builds and pushes the three images to ECR with an immutable git-SHA tag. UNTESTED. Requires Docker + AWS CLI.
# Pushing images costs a few cents of ECR storage; it does NOT create or change infrastructure.
# Prereq: `terraform apply` of ONLY the ECR repos first (see docs/DEPLOYMENT.md step 3), or the full stack with a placeholder tag.
set -euo pipefail
[ "${CONFIRM:-}" = "yes" ] || { echo "Refusing to push. Re-run with CONFIRM=yes after reading docs/DEPLOYMENT.md"; exit 1; }
cd "$(dirname "$0")/.."
git diff --quiet || { echo "Working tree dirty; commit first so the tag identifies the code."; exit 1; }
TAG="$(git rev-parse --short HEAD)"
REGION="${AWS_REGION:-ap-south-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REG="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REG"
for svc in api ingest forecast; do
  docker build -f services/Dockerfile --target "$svc" -t "$REG/floodres-demo-$svc:$TAG" .
  docker push "$REG/floodres-demo-$svc:$TAG"
done
echo "Pushed tag: $TAG   ->  use  image_tag = \"$TAG\"  in terraform.tfvars"
