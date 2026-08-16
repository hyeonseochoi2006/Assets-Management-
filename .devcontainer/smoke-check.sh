#!/usr/bin/env bash
set -u

API_PORT="${ASSET_API_PORT:-8000}"
HQ_PORT="${ASSET_HQ_PORT:-5173}"

fail=0

check() {
  local name="$1"
  local url="$2"

  if curl -fsS "$url" >/dev/null 2>&1; then
    echo "PASS  $name  $url"
  else
    echo "FAIL  $name  $url"
    fail=1
  fi
}

check "FastAPI health" "http://127.0.0.1:${API_PORT}/api/v1/health"
check "Daily history API" "http://127.0.0.1:${API_PORT}/api/v1/operations/daily/history"
check "CEO approval queue" "http://127.0.0.1:${API_PORT}/api/v1/approvals?limit=1"
check "React HQ" "http://127.0.0.1:${HQ_PORT}"

if [ "$fail" -ne 0 ]; then
  echo "Smoke check failed. Review /tmp/asset-hq-api.log and /tmp/asset-hq-frontend.log."
  exit 1
fi

echo "HQ smoke check passed. Primary ports: ${HQ_PORT} (React), ${API_PORT} (FastAPI)."
