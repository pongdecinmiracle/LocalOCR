# LocalOCR launcher (PowerShell) — builds and starts all services via Docker.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Host "Docker is required. Install Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
  exit 1
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example — review it (set a strong POSTGRES_PASSWORD / LOCALOCR_SECRET_KEY)." -ForegroundColor Yellow
}

$port = (Select-String -Path ".env" -Pattern '^\s*LOCALOCR_PORT\s*=\s*(\d+)' |
  Select-Object -First 1).Matches.Groups[1].Value
if (-not $port) { $port = "8080" }

Write-Host "Building and starting LocalOCR services..." -ForegroundColor Cyan
docker compose up -d --build

Write-Host "LocalOCR running at http://localhost:$port" -ForegroundColor Green
Write-Host "First run only — pull the vision model:  docker compose exec ollama ollama pull qwen2.5vl:7b" -ForegroundColor DarkGray
Start-Process "http://localhost:$port"
