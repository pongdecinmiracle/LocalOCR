# Back up LocalOCR: a Postgres dump + an archive of the user-files volume.
# Run from the repo root while the stack is up.
$ErrorActionPreference = "Stop"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "localocr" }
$pgDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "localocr" }
New-Item -ItemType Directory -Force backups | Out-Null

docker compose exec -T db pg_dump -U $pgUser --format=custom --file=/tmp/db.dump $pgDb
docker compose cp "db:/tmp/db.dump" "backups/db_$stamp.dump"
docker compose exec -T db rm -f /tmp/db.dump

docker run --rm `
    -v localocr_file_data:/data:ro `
    -v "${PWD}\backups:/backup" `
    alpine tar czf "/backup/files_$stamp.tgz" -C /data .

Write-Host "Backup complete:"
Write-Host "  backups\db_$stamp.dump"
Write-Host "  backups\files_$stamp.tgz"
