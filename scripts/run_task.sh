#!/usr/bin/env bash
# One-off ECS tasks inside the VPC (the database is private). UNTESTED.
#   CONFIRM=yes scripts/run_task.sh migrate
#   CONFIRM=yes scripts/run_task.sh dbuser        # creates the least-privilege DB login from the db-app secret
#   CONFIRM=yes DEMO_AS_OF=2024-09-28T20:00:00+00:00 scripts/run_task.sh seed
#   CONFIRM=yes scripts/run_task.sh ingest        # runs the scheduled ingest task once, now
set -euo pipefail
[ "${CONFIRM:-}" = "yes" ] || { echo "Starts a billable Fargate task. Re-run with CONFIRM=yes"; exit 1; }
cd "$(dirname "$0")/.."
tf() { terraform -chdir=infra/aws output -raw "$1"; }
CLUSTER="$(tf cluster)"; SUBNETS="$(tf subnets)"; SG="$(tf service_sg)"; FAMILY="$(tf api_task_family)"
case "${1:-}" in
  migrate) CMD='null'; TD="$(tf migrate_task_family)"; NAME=migrate ;;   # master login; command baked into the task definition
  dbuser)  CMD='null'; TD="$(tf migrate_task_family)"; NAME=migrate; EXTRA='"command":["python","-m","floodcommon.create_app_user"]' ;;
  seed)    CMD='["python","-m","ingest.seed_demo"]';      TD="$FAMILY"; NAME=api ;;
  ingest)  CMD='null'; TD="${FAMILY%-api}-ingest"; NAME=ingest ;;
  *) echo "usage: run_task.sh migrate|dbuser|seed|ingest"; exit 2 ;;
esac
OVR="{\"containerOverrides\":[{\"name\":\"$NAME\""
[ "$CMD" != "null" ] && OVR="$OVR,\"command\":$CMD"
[ -n "${EXTRA:-}" ] && OVR="$OVR,$EXTRA"
[ "${1}" = seed ] && OVR="$OVR,\"environment\":[{\"name\":\"DEMO_AS_OF\",\"value\":\"${DEMO_AS_OF:-2024-09-28T20:00:00+00:00}\"}]"
OVR="$OVR}]}"
ARN="$(aws ecs run-task --cluster "$CLUSTER" --launch-type FARGATE --task-definition "$TD" \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides "$OVR" --query 'tasks[0].taskArn' --output text)"
echo "started $ARN"; aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$ARN"
aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$ARN" --query 'tasks[0].containers[*].[name,exitCode,reason]' --output text
