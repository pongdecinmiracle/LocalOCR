# LocalOCR stopper (PowerShell) — stops all services.
$ErrorActionPreference = "SilentlyContinue"
Set-Location $PSScriptRoot

docker compose down
Write-Host "[OK] LocalOCR services stopped (data is preserved in Docker volumes)." -ForegroundColor Green
Write-Host "      To also wipe all data:  docker compose down -v" -ForegroundColor DarkGray
