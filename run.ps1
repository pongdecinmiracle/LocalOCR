# LocalOCR launcher (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Ensure Ollama is running
$ollama = Get-Process ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
  Write-Host "Starting Ollama..." -ForegroundColor Cyan
  Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
  Start-Sleep -Seconds 2
}

Write-Host "LocalOCR running at http://127.0.0.1:8000" -ForegroundColor Green
Start-Process "http://127.0.0.1:8000"

& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
