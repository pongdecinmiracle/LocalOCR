#!/bin/sh
set -e

# Started as root: make sure the data volume belongs to the unprivileged app
# user (cheap no-op when already owned), then drop privileges for everything.
RUNAS=""
if [ "$(id -u)" = "0" ]; then
    mkdir -p /data
    if [ "$(stat -c %U /data)" != "app" ]; then
        chown -R app:app /data
    fi
    RUNAS="gosu app"
fi

# Apply database migrations once, before any workers start, so multiple
# uvicorn workers don't race on schema changes.
$RUNAS python -m app.migrate

# --proxy-headers trusts X-Forwarded-* from nginx so rate limiting and logs
# see real client IPs.
exec $RUNAS uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WEB_CONCURRENCY:-4}" \
    --proxy-headers \
    --forwarded-allow-ips '*'
