#!/bin/sh
set -eu

: "${1:?Usage: restore_postgres.sh <backup-file>}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"

if [ "${CONFIRM_RESTORE:-}" != "${POSTGRES_DB}" ]; then
  echo "Set CONFIRM_RESTORE=${POSTGRES_DB} to confirm this destructive restore." >&2
  exit 1
fi

pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  --dbname="${POSTGRES_DB}" \
  "$1"

echo "Restore completed for ${POSTGRES_DB}"
