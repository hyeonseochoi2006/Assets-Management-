#!/usr/bin/env bash
set -u

API_PORT="${ASSET_API_PORT:-8000}"
HQ_PORT="${ASSET_HQ_PORT:-5173}"

fail=0

if [ -z "${ASSET_API_TOKEN:-}" ] || [ "${#ASSET_API_TOKEN}" -lt 32 ]; then
  echo "FAIL  ASSET_API_TOKEN is missing or shorter than 32 characters"
  exit 1
fi

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

check_status() {
  local name="$1"
  local expected="$2"
  local url="$3"
  shift 3

  local actual
  actual="$(curl -sS -o /dev/null -w '%{http_code}' "$@" "$url" 2>/dev/null || true)"
  if [ "$actual" = "$expected" ]; then
    echo "PASS  $name  HTTP $actual"
  else
    echo "FAIL  $name  expected HTTP $expected, received ${actual:-no response}"
    fail=1
  fi
}

check "FastAPI health" "http://127.0.0.1:${API_PORT}/api/v1/health"
check_status \
  "Unauthenticated API is blocked" \
  "401" \
  "http://127.0.0.1:${API_PORT}/api/v1/operations/daily/history"
check_status \
  "Wrong API token is blocked" \
  "401" \
  "http://127.0.0.1:${API_PORT}/api/v1/approvals?limit=1" \
  -H "Authorization: Bearer wrong-token"
check_status \
  "Valid API token is accepted" \
  "200" \
  "http://127.0.0.1:${API_PORT}/api/v1/auth/check" \
  -H "Authorization: Bearer ${ASSET_API_TOKEN}"
check_status \
  "Daily history API" \
  "200" \
  "http://127.0.0.1:${API_PORT}/api/v1/operations/daily/history" \
  -H "Authorization: Bearer ${ASSET_API_TOKEN}"
check_status \
  "Daily schedule API" \
  "200" \
  "http://127.0.0.1:${API_PORT}/api/v1/operations/daily/schedule" \
  -H "Authorization: Bearer ${ASSET_API_TOKEN}"
check_status \
  "CEO approval queue" \
  "200" \
  "http://127.0.0.1:${API_PORT}/api/v1/approvals?limit=1" \
  -H "Authorization: Bearer ${ASSET_API_TOKEN}"
check "React HQ" "http://127.0.0.1:${HQ_PORT}"

if [ "$fail" -ne 0 ]; then
  echo "Smoke check failed. Review /tmp/asset-hq-api.log and /tmp/asset-hq-frontend.log."
  exit 1
fi

echo "HQ smoke check passed. Primary ports: ${HQ_PORT} (React), ${API_PORT} (FastAPI)."
