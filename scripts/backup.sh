#!/bin/sh
# Back up LocalOCR: a Postgres dump + an archive of the user-files volume.
# Run from the repo root while the stack is up. Restores:
#   db:    docker compose exec -T db pg_restore -U localocr -d localocr --clean /tmp/db.dump
#   files: docker run --rm -v localocr_file_data:/data -v "$PWD/backups:/backup" alpine \
#            tar xzf "/backup/<files archive>" -C /data
set -e

STAMP=$(date +%Y%m%d_%H%M%S)
PGUSER="${POSTGRES_USER:-localocr}"
PGDB="${POSTGRES_DB:-localocr}"
mkdir -p backups

docker compose exec -T db pg_dump -U "$PGUSER" --format=custom --file=/tmp/db.dump "$PGDB"
docker compose cp "db:/tmp/db.dump" "backups/db_${STAMP}.dump"
docker compose exec -T db rm -f /tmp/db.dump

docker run --rm \
    -v localocr_file_data:/data:ro \
    -v "$(pwd)/backups:/backup" \
    alpine tar czf "/backup/files_${STAMP}.tgz" -C /data .

echo "Backup complete:"
echo "  backups/db_${STAMP}.dump"
echo "  backups/files_${STAMP}.tgz"
