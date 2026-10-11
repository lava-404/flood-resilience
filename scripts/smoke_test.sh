#!/usr/bin/env bash
# HTTP smoke test for a local or deployed API. Needs only curl + python3. UNTESTED against a running server.
#   API_URL=http://localhost:8000 scripts/smoke_test.sh
set -euo pipefail
API="${API_URL:?set API_URL}"; LAT="${LAT:-26.15}"; LON="${LON:-85.90}"; fail=0
check() { # name url jq-ish python expression over parsed JSON "j"
  local body; body="$(curl -fsS --max-time 10 "$2")" || { echo "FAIL $1 (http)"; fail=1; return; }
  python3 -c "import json,sys; j=json.loads(sys.argv[1]); sys.exit(0 if ($3) else 1)" "$body" \
    && echo "ok   $1" || { echo "FAIL $1 :: $body" | cut -c1-300; fail=1; }
}
check healthz      "$API/healthz"                              'j["status"]=="ok"'
check readyz       "$API/readyz"                               'j["status"]=="ready"'
check risk         "$API/v1/risk?lat=$LAT&lon=$LON"            'j["state"] in ("SAFE","WATCH","WARNING","EVACUATE") and "model_version" in j'
check source-health "$API/v1/source-health"                    'isinstance(j,list) and len(j)>0'
check shelters     "$API/v1/shelters/nearby?lat=$LAT&lon=$LON" 'isinstance(j,list)'
[ "$fail" = 0 ] && echo "SMOKE PASSED" || { echo "SMOKE FAILED"; exit 1; }
