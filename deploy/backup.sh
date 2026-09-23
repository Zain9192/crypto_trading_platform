#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/crypto-platform

if test -f restic.env; then
    set -a
    source ./restic.env
    set +a
fi

: "${RESTIC_REPOSITORY:?Set an offsite RESTIC_REPOSITORY}"
: "${RESTIC_PASSWORD_FILE:?Set RESTIC_PASSWORD_FILE}"
if [[ ! "$RESTIC_REPOSITORY" =~ ^(s3|sftp|rest|b2|azure|gs|rclone): ]]; then
    echo 'Backup repository must be offsite' >&2
    exit 1
fi
command -v restic >/dev/null
command -v flock >/dev/null
exec 9>/opt/crypto-platform/.backup.lock
flock -n 9 || { echo 'Backup already running' >&2; exit 1; }

compose=(docker compose --env-file .env.production --env-file .release.env -f compose.prod.yml)
folder=$(mktemp -d /var/tmp/crypto-backup.XXXXXXXX)
trap 'rm -rf "$folder"' EXIT
"${compose[@]}" exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$folder/postgres.dump"
"${compose[@]}" exec -T mongodb sh -c 'exec mongodump -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --archive --gzip --quiet' > "$folder/mongodb.archive.gz"
"${compose[@]}" exec -T backend tar -C /app/model_artifacts -czf - . > "$folder/model_artifacts.tar.gz"
test -s "$folder/postgres.dump" && test -s "$folder/mongodb.archive.gz" && test -s "$folder/model_artifacts.tar.gz"
restic backup --tag crypto-platform "$folder"
restic forget --tag crypto-platform --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
