#!/usr/bin/env bash
# Starts the local stack in Docker, seeds the SYNTHETIC replay, then runs the end-to-end test. NEVER EXECUTED by its author.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo "Docker not found (docs/MACOS_SETUP.md section 3)"; exit 1; }
python3 -c "import cryptography" 2>/dev/null || { echo "pip install cryptography   (or activate the venv from docs/MACOS_SETUP.md)"; exit 1; }
docker compose up --build -d db localstack localstack-init migrate api forecast seed
echo "waiting for the API..."; for i in $(seq 1 60); do curl -fsS localhost:8000/healthz >/dev/null 2>&1 && break; sleep 2; done
python3 scripts/e2e_local.py || { echo; echo "FAILED. Logs:"; docker compose logs --tail=40 migrate seed api forecast; exit 1; }
