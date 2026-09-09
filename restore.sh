
set -euo pipefail

DB_USER="${DB_USER:-barq_app}"
DB_NAME="${DB_NAME:-barq_tasks}"
HOST_FILE="${1:?Usage: ./restore.sh path/to/backup.dump}"
CONTAINER_FILE="/tmp/barq_restore_$(date -u +%s).dump"

if [ ! -f "$HOST_FILE" ]; then
    echo "[FAIL] backup file not found: $HOST_FILE" >&2
    exit 1
fi

if ! docker inspect postgres >/dev/null 2>&1; then
    echo "[FAIL] postgres container not found. Is docker compose up running?" >&2
    exit 1
fi

echo "Copying $HOST_FILE into the postgres container..."
docker cp "$HOST_FILE" "postgres:${CONTAINER_FILE}"

echo "Restoring into database '$DB_NAME' (--clean --if-exists: safe to re-run)..."
docker exec postgres pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists "$CONTAINER_FILE"

docker exec postgres rm -f "$CONTAINER_FILE"

echo "[OK] Restore complete from $HOST_FILE"