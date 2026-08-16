#!/usr/bin/env bash
set -u

START_LOG="/tmp/asset-ceo-start.log"
API_LOG="/tmp/asset-hq-api.log"
HQ_LOG="/tmp/asset-hq-frontend.log"

API_PORT="${ASSET_API_PORT:-8000}"
HQ_PORT="${ASSET_HQ_PORT:-5173}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

{
  echo "[$(date -Iseconds)] Asset Management HQ start requested"
  echo "repo_root=$REPO_ROOT api_port=$API_PORT hq_port=$HQ_PORT"
} >>"$START_LOG"

BRANCH="$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || true)"
if [ "$BRANCH" = "main" ]; then
  export ASSET_ENV="PRODUCTION"
else
  export ASSET_ENV="DEVELOPMENT"
fi
export ASSET_BRANCH="$BRANCH"
export ASSET_API_PORT="$API_PORT"
export ASSET_HQ_PORT="$HQ_PORT"

cd "$REPO_ROOT/asset-agent" || {
  echo "[$(date -Iseconds)] ERROR: asset-agent directory not found" >>"$START_LOG"
  exit 1
}

# Primary backend: FastAPI
if curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/health" >/dev/null 2>&1; then
  echo "[$(date -Iseconds)] HQ API already healthy on ${API_PORT}" >>"$START_LOG"
else
  if python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    nohup python -m uvicorn api.app:app \
      --host 0.0.0.0 \
      --port "$API_PORT" \
      >"$API_LOG" 2>&1 &

    API_PID=$!
    echo "[$(date -Iseconds)] HQ API launched pid=$API_PID branch=$BRANCH mode=$ASSET_ENV port=$API_PORT" >>"$START_LOG"
  else
    echo "[$(date -Iseconds)] ERROR: fastapi/uvicorn not installed; run pip install -r asset-agent/requirements.txt" >>"$START_LOG"
  fi
fi

# Primary frontend: React/Vite HQ
if curl -fsS "http://127.0.0.1:${HQ_PORT}" >/dev/null 2>&1; then
  echo "[$(date -Iseconds)] React HQ already healthy on ${HQ_PORT}" >>"$START_LOG"
else
  if [ -d "$REPO_ROOT/asset-hq/node_modules" ]; then
    cd "$REPO_ROOT/asset-hq" || exit 1
    nohup npm run dev -- --host 0.0.0.0 --port "$HQ_PORT" \
      >"$HQ_LOG" 2>&1 &

    HQ_PID=$!
    echo "[$(date -Iseconds)] React HQ launched pid=$HQ_PID branch=$BRANCH mode=$ASSET_ENV port=$HQ_PORT" >>"$START_LOG"
  else
    echo "[$(date -Iseconds)] ERROR: asset-hq/node_modules missing; run npm --prefix asset-hq install" >>"$START_LOG"
  fi
fi

# Streamlit CEO Desk remains available only as a manual fallback.
echo "[$(date -Iseconds)] Streamlit backup is not auto-started. Use .devcontainer/start-streamlit-backup.sh if needed." >>"$START_LOG"
