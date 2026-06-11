#!/usr/bin/env bash
# LocalOCR stopper (Linux / macOS) — stops all services.
set -euo pipefail
cd "$(dirname "$0")"

docker compose down
echo "[OK] LocalOCR services stopped (data preserved in Docker volumes)."
echo "      To also wipe all data:  docker compose down -v"
