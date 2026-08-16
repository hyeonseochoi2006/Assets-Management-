#!/usr/bin/env bash
set -u

START_LOG="/tmp/asset-ceo-start.log"
APP_LOG="/tmp/asset-ceo-desk.log"

# Resolve the repository from this script's own location instead of assuming
# the Codespaces lifecycle command starts inside the Git repository.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

{
  echo "[$(date -Iseconds)] CEO Desk start requested"
  echo "repo_root=$REPO_ROOT"
} >>"$START_LOG"

if pgrep -f "streamlit run ceo_desk/app.py" >/dev/null 2>&1; then
  echo "[$(date -Iseconds)] CEO Desk already running" >>"$START_LOG"
  exit 0
fi

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

nohup python -m streamlit run ceo_desk/app.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true \
  >"$APP_LOG" 2>&1 &

PID=$!
echo "[$(date -Iseconds)] CEO Desk launched pid=$PID branch=$BRANCH mode=$ASSET_ENV" >>"$START_LOG"
