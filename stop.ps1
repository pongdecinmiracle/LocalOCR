# LocalOCR stopper (PowerShell)
$ErrorActionPreference = "SilentlyContinue"

# Find the LocalOCR web server (uvicorn running main:app).
$procs = Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Where-Object { $_.CommandLine -like '*uvicorn*' -and $_.CommandLine -like '*main:app*' }

if ($procs) {
  $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  Write-Host "[OK] LocalOCR server stopped." -ForegroundColor Green
} else {
  Write-Host "[i] LocalOCR server was not running." -ForegroundColor Yellow
}

Write-Host "Note: Ollama is left running (it's a shared service)." -ForegroundColor DarkGray
Write-Host "      To stop it too:  Get-Process ollama | Stop-Process" -ForegroundColor DarkGray
