#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY}"
: "${RESTIC_PASSWORD_FILE:?Set RESTIC_PASSWORD_FILE}"
folder=$(mktemp -d /var/tmp/crypto-verify.XXXXXXXX)
trap 'rm -rf "$folder"' EXIT
restic check
restic restore latest --tag crypto-platform --target "$folder"
pg_dump_file=$(find "$folder" -type f -name postgres.dump -print -quit)
mongo_file=$(find "$folder" -type f -name mongodb.archive.gz -print -quit)
artifacts_file=$(find "$folder" -type f -name model_artifacts.tar.gz -print -quit)
test -n "$pg_dump_file" && test -n "$mongo_file" && test -n "$artifacts_file"
docker run --rm --network none -v "$pg_dump_file:/backup.dump:ro" postgres:16-alpine pg_restore --list /backup.dump >/dev/null
gzip -t "$mongo_file"
tar -tzf "$artifacts_file" >/dev/null
echo 'Latest PostgreSQL, MongoDB and model artifact archives verified'
