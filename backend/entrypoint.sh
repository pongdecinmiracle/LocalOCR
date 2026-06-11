#!/bin/sh
set -e

# Create database tables (idempotent) once, before any workers start, so
# multiple uvicorn workers don't race to CREATE TABLE on a fresh database.
python -m app.init_db

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WEB_CONCURRENCY:-2}"
