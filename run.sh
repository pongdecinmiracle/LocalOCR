#!/usr/bin/env bash
# LocalOCR launcher (Linux / macOS)
set -euo pipefail
cd "$(dirname "$0")"

HOST="${LOCALOCR_HOST:-127.0.0.1}"   # set to 0.0.0.0 to expose on the network
PORT="${LOCALOCR_PORT:-8000}"
OLLAMA="${OLLAMA_HOST:-http://127.0.0.1:11434}"

# Start Ollama if it isn't already responding.
if ! curl -sf "${OLLAMA}/api/tags" >/dev/null 2>&1; then
  echo "Starting Ollama..."
  nohup ollama serve >/tmp/localocr-ollama.log 2>&1 &
  sleep 2
fi

# Pick the venv python if present, else system python3.
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

echo "LocalOCR running at http://${HOST}:${PORT}"
exec "$PY" -m uvicorn main:app --app-dir backend --host "$HOST" --port "$PORT"
