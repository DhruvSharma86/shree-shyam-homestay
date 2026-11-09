#!/usr/bin/env bash
# Create a PostgreSQL logical backup. Safe defaults: explicit target,
# password via PG* env only (never printed), non-zero exit on failure.
set -euo pipefail
DB_NAME="${1:?Usage: backup-postgres.sh <db-name> [output-dir] [retention-days]}"
OUTPUT_DIR="${2:-./backups}"
RETENTION_DAYS="${3:-30}"
command -v pg_dump >/dev/null || { echo "pg_dump not found" >&2; exit 1; }
[ -n "${PGPASSWORD:-}" ] || { echo "PGPASSWORD is not set" >&2; exit 1; }
mkdir -p "$OUTPUT_DIR"
OUT_FILE="${OUTPUT_DIR}/${DB_NAME}_backup_$(date +%Y%m%d_%H%M%S).dump"
echo "Backing up database '${DB_NAME}' -> ${OUT_FILE}"
pg_dump -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER:?PGUSER is required}" -d "$DB_NAME" -Fc -f "$OUT_FILE"
[ -s "$OUT_FILE" ] || { echo "Backup file is missing or empty" >&2; exit 1; }
echo "Backup OK: ${OUT_FILE} (restrict permissions; contains guest + financial data)"
find "$OUTPUT_DIR" -name "${DB_NAME}_backup_*.dump" -mtime +"${RETENTION_DAYS}" -delete
echo "PASS: backup complete."
