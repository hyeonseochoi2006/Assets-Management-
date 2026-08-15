#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if pgrep -f "streamlit run ceo_desk/app.py" >/dev/null 2>&1; then
  exit 0
fi

BRANCH="$(git branch --show-current 2>/dev/null || true)"
if [ "$BRANCH" = "main" ]; then
  export ASSET_ENV="PRODUCTION"
else
  export ASSET_ENV="DEVELOPMENT"
fi
export ASSET_BRANCH="$BRANCH"

cd "$REPO_ROOT/asset-agent"
nohup python -m streamlit run ceo_desk/app.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true \
  >/tmp/asset-ceo-desk.log 2>&1 &
