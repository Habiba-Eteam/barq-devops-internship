

set -uo pipefail
export MSYS_NO_PATHCONV=1

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
READY_TIMEOUT="${READY_TIMEOUT:-60}"

PASS_COUNT=0
FAIL_COUNT=0
pass() { echo "[PASS] $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "[FAIL] $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

is_ready_check() {
    curl -sf --max-time 5 "$BASE_URL/ready" | grep -q '"status":"ready"'
}

wait_until() {
    local description="$1" timeout="$2" cmd="$3"
    local start
    start=$(date +%s)
    while true; do
        if eval "$cmd" >/dev/null 2>&1; then
            return 0
        fi
        if (( $(date +%s) - start >= timeout )); then
            echo "  (timed out after ${timeout}s waiting for: $description)"
            return 1
        fi
        sleep 1
    done
}

echo " BARQ persistence_test.sh — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo " Base URL: $BASE_URL"

echo
echo " Creating a marker record "
MARKER="persistence-test-$(date +%s)"
create_body=$(curl -s --max-time 5 -X POST "$BASE_URL/records" \
    -H "Content-Type: application/json" \
    -d "{\"title\":\"$MARKER\"}")
if echo "$create_body" | grep -q "\"title\":\"$MARKER\""; then
    pass "created record with marker: $MARKER"
else
    fail "could not create marker record -- aborting: $create_body"
    exit 1
fi

echo
echo " docker compose down "
if docker compose down; then
    pass "docker compose down succeeded"
else
    fail "docker compose down failed -- aborting"
    exit 1
fi

vol_exists=$(docker volume ls -q --filter name=postgres-data)
if [ -n "$vol_exists" ]; then
    pass "postgres-data volume still exists after down: $vol_exists"
else
    fail "postgres-data volume is gone after down (was -v used somewhere?)"
fi

echo
echo " docker compose up --build -d "
if docker compose up --build -d; then
    pass "docker compose up --build -d succeeded"
else
    fail "docker compose up failed -- aborting"
    exit 1
fi

if wait_until "service ready" "$READY_TIMEOUT" "is_ready_check"; then
    pass "service reports ready again within ${READY_TIMEOUT}s"
else
    fail "service did not become ready within ${READY_TIMEOUT}s"
fi

echo
echo " Verifying the marker record survived "
list_body=$(curl -s --max-time 5 "$BASE_URL/records")
if echo "$list_body" | grep -q "\"title\":\"$MARKER\""; then
    pass "marker record '$MARKER' is still present after container recreation"
else
    fail "marker record '$MARKER' was NOT found after container recreation"
fi

echo " Summary: $PASS_COUNT passed, $FAIL_COUNT failed"


if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0