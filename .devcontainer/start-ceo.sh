#!/usr/bin/env bash
set -u

START_LOG="/tmp/asset-ceo-start.log"
APP_LOG="/tmp/asset-ceo-desk.log"
API_LOG="/tmp/asset-hq-api.log"
HQ_LOG="/tmp/asset-hq-frontend.log"

# Resolve the repository from this script's own location instead of assuming
# the Codespaces lifecycle command starts inside the Git repository.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

{
  echo "[$(date -Iseconds)] Asset Management services start requested"
  echo "repo_root=$REPO_ROOT"
} >>"$START_LOG"

BRANCH="$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || true)"
if [ "$BRANCH" = "main" ]; then
  export ASSET_ENV="PRODUCTION"
else
  export ASSET_ENV="DEVELOPMENT"
fi
export ASSET_BRANCH="$BRANCH"

cd "$REPO_ROOT/asset-agent" || {
  echo "[$(date -Iseconds)] ERROR: asset-agent directory not found" >>"$START_LOG"
  exit 1
}

# CEO Desk / Streamlit backup UI
if curl -fsS http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
  echo "[$(date -Iseconds)] CEO Desk already healthy on 8501" >>"$START_LOG"
else
  nohup python -m streamlit run ceo_desk/app.py \
    --server.address 0.0.0.0 \
    --server.port 8501 \
    --server.headless true \
    >"$APP_LOG" 2>&1 &

  DESK_PID=$!
  echo "[$(date -Iseconds)] CEO Desk launched pid=$DESK_PID branch=$BRANCH mode=$ASSET_ENV" >>"$START_LOG"
fi

# Frontend bridge / FastAPI
if curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
  echo "[$(date -Iseconds)] HQ API already healthy on 8000" >>"$START_LOG"
else
  if python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    nohup python -m uvicorn api.app:app \
      --host 0.0.0.0 \
      --port 8000 \
      >"$API_LOG" 2>&1 &

    API_PID=$!
    echo "[$(date -Iseconds)] HQ API launched pid=$API_PID branch=$BRANCH mode=$ASSET_ENV" >>"$START_LOG"
  else
    echo "[$(date -Iseconds)] ERROR: fastapi/uvicorn not installed; run pip install -r asset-agent/requirements.txt" >>"$START_LOG"
  fi
fi

# React Asset Management HQ
if curl -fsS http://127.0.0.1:5173 >/dev/null 2>&1; then
  echo "[$(date -Iseconds)] React HQ already healthy on 5173" >>"$START_LOG"
else
  if [ -d "$REPO_ROOT/asset-hq/node_modules" ]; then
    cd "$REPO_ROOT/asset-hq" || exit 1
    nohup npm run dev -- --host 0.0.0.0 --port 5173 \
      >"$HQ_LOG" 2>&1 &

    HQ_PID=$!
    echo "[$(date -Iseconds)] React HQ launched pid=$HQ_PID branch=$BRANCH mode=$ASSET_ENV" >>"$START_LOG"
  else
    echo "[$(date -Iseconds)] ERROR: asset-hq/node_modules missing; run npm --prefix asset-hq install" >>"$START_LOG"
  fi
fi
