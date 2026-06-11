@echo off
cd /d "%~dp0"
where docker >NUL 2>&1
if errorlevel 1 (
  echo Docker is required. Install Docker Desktop: https://www.docker.com/products/docker-desktop/
  exit /b 1
)
if not exist ".env" (
  copy ".env.example" ".env" >NUL
  echo Created .env from .env.example - review it before going to production.
)
echo Building and starting LocalOCR services...
docker compose up -d --build
echo LocalOCR running at http://localhost:8080  (or your LOCALOCR_PORT)
echo First run only - pull the model:  docker compose exec ollama ollama pull qwen2.5vl:7b
start "" http://localhost:8080
