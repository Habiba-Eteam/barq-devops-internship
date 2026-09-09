
set -euo pipefail
export MSYS_NO_PATHCONV=1

DB_USER="${DB_USER:-barq_app}"
DB_NAME="${DB_NAME:-barq_tasks}"
BACKUP_DIR="backups"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
CONTAINER_FILE="/tmp/barq_backup_${TIMESTAMP}.dump"
HOST_FILE="${BACKUP_DIR}/barq_tasks_${TIMESTAMP}.dump"

if ! docker inspect postgres >/dev/null 2>&1; then
    echo "[FAIL] postgres container not found. Is docker compose up running?" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"

echo "Backing up database '$DB_NAME' from container 'postgres'..."
docker exec postgres pg_dump -U "$DB_USER" -d "$DB_NAME" -F c -f "$CONTAINER_FILE"

echo "Copying dump out of the container..."
docker cp "postgres:${CONTAINER_FILE}" "$HOST_FILE"

docker exec postgres rm -f "$CONTAINER_FILE"

size=$(du -h "$HOST_FILE" | cut -f1)
echo "[OK] Backup written to $HOST_FILE ($size)"