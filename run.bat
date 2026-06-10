@echo off
cd /d "%~dp0"
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I "ollama.exe" >NUL
if errorlevel 1 (
  echo Starting Ollama...
  start "" /B ollama serve
  timeout /t 2 >NUL
)
echo LocalOCR running at http://127.0.0.1:8000
start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
