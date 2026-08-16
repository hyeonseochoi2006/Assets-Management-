#!/usr/bin/env bash
set -u

STREAMLIT_PORT="${ASSET_STREAMLIT_PORT:-8501}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_LOG="/tmp/asset-ceo-desk.log"

cd "$REPO_ROOT/asset-agent" || exit 1

if curl -fsS "http://127.0.0.1:${STREAMLIT_PORT}/_stcore/health" >/dev/null 2>&1; then
  echo "Streamlit backup is already running on port ${STREAMLIT_PORT}."
  exit 0
fi

nohup python -m streamlit run ceo_desk/app.py \
  --server.address 0.0.0.0 \
  --server.port "$STREAMLIT_PORT" \
  --server.headless true \
  >"$APP_LOG" 2>&1 &

echo "Streamlit backup started on port ${STREAMLIT_PORT}. PID=$!"
echo "Log: ${APP_LOG}"
