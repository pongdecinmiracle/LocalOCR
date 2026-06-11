@echo off
cd /d "%~dp0"
docker compose down
echo [OK] LocalOCR services stopped (data preserved in Docker volumes).
echo      To also wipe all data:  docker compose down -v
