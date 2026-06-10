#!/usr/bin/env bash
# LocalOCR stopper (Linux / macOS)
pids=$(pgrep -f 'uvicorn main:app' || true)
if [ -n "$pids" ]; then
  kill $pids
  echo "[OK] LocalOCR server stopped."
else
  echo "[i] LocalOCR server was not running."
fi
echo "Note: Ollama is left running. To stop it too: pkill ollama"
