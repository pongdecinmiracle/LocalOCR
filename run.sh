#!/usr/bin/env bash
# LocalOCR launcher (Linux / macOS) — builds and starts all services via Docker.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Engine / Docker Desktop first." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — set a strong POSTGRES_PASSWORD / LOCALOCR_SECRET_KEY before production."
fi

PORT="$(grep -E '^\s*LOCALOCR_PORT\s*=' .env | head -n1 | cut -d= -f2 | tr -d '[:space:]')"
PORT="${PORT:-8080}"

echo "Building and starting LocalOCR services..."
docker compose up -d --build

echo "LocalOCR running at http://localhost:${PORT}"
echo "First run only — pull the vision model:  docker compose exec ollama ollama pull qwen2.5vl:7b"
