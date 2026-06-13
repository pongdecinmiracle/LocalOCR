FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

# curl is only used by the container healthcheck; gosu lets the entrypoint fix
# /data ownership as root, then drop to the unprivileged app user. PyMuPDF,
# Pillow and psycopg[binary] ship manylinux wheels that bundle their native
# libs, so no extra build/system packages are required.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --user-group --home /srv --shell /usr/sbin/nologin app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini entrypoint.sh ./
RUN chmod +x entrypoint.sh

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
