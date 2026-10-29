#!/bin/sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILENAME="${POSTGRES_DB}-${TIMESTAMP}.dump"
FILE_PATH="${BACKUP_DIR}/${FILENAME}"

umask 077
mkdir -p "${BACKUP_DIR}"

pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --file="${FILE_PATH}" \
  "${POSTGRES_DB}"

echo "Backup written to ${FILE_PATH}"

if [ -n "${BACKUP_S3_URI:-}" ]; then
  aws s3 cp "${FILE_PATH}" "${BACKUP_S3_URI%/}/${FILENAME}" --only-show-errors
  echo "Backup uploaded to ${BACKUP_S3_URI%/}/${FILENAME}"
fi
