#!/usr/bin/env bash
# Restore a PostgreSQL logical backup into an EXPLICITLY named target.
# Refuses to overwrite a production-named database unless --allow-production
# is given. Password via PG* env only (never printed). No destructive default.
set -euo pipefail
USAGE="Usage: restore-postgres.sh <backup-file> <target-db> [--allow-production] [--holder production-db-name]"
echo "$USAGE" >&2
BACKUP_FILE="${1:-}"
TARGET_DB="${2:-}"
ALLOW_PROD=0
PROD_NAME="shree_shyam"
for arg in "$@"; do
  if [ "$arg" = "--allow-production" ]; then ALLOW_PROD=1; fi
done
[ -n "$BACKUP_FILE" ] && [ -n "$TARGET_DB" ] || { echo "$USAGE" >&2; exit 1; }
[ -s "$BACKUP_FILE" ] || { echo "Backup file is missing or empty: $BACKUP_FILE" >&2; exit 1; }
command -v pg_restore >/dev/null || { echo "pg_restore not found" >&2; exit 1; }
[ -n "${PGPASSWORD:-}" ] || { echo "PGPASSWORD is not set" >&2; exit 1; }
if [ "$TARGET_DB" = "$PROD_NAME" ] && [ "$ALLOW_PROD" -ne 1 ]; then
  echo "Refusing to restore into production-named database '${TARGET_DB}' without --allow-production." >&2
  exit 1
fi
echo "Restoring '${BACKUP_FILE}' -> database '${TARGET_DB}' (host ${PGHOST:-localhost})"
psql -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER:?PGUSER is required}" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${TARGET_DB}' AND pid <> pg_backend_pid();" >/dev/null
psql -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER}" -d postgres \
  -c "DROP DATABASE IF EXISTS \"${TARGET_DB}\";" >/dev/null
psql -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER}" -d postgres \
  -c "CREATE DATABASE \"${TARGET_DB}\";" >/dev/null
pg_restore -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER}" -d "$TARGET_DB" "$BACKUP_FILE"
echo "Restore complete. Verify before trusting it:"
echo "  psql -h \"\${PGHOST:-localhost}\" -U \"\${PGUSER}\" -d \"${TARGET_DB}\" -c \"SELECT count(*) FROM bookings;\""
echo "PASS: restore complete."
