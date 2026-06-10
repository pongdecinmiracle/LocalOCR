@echo off
REM LocalOCR stopper — double-click to stop the web server.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
echo.
pause
