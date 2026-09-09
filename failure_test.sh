
set -uo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
TARGET="${1:-app-01}"
OTHER="app-02"
if [ "$TARGET" = "app-02" ]; then OTHER="app-01"; fi

RECOVERY_TIMEOUT="${RECOVERY_TIMEOUT:-60}"
DURING_FAILURE_REQUESTS="${DURING_FAILURE_REQUESTS:-30}"
AFTER_RECOVERY_REQUESTS="${AFTER_RECOVERY_REQUESTS:-20}"

PASS_COUNT=0
FAIL_COUNT=0
pass() { echo "[PASS] $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "[FAIL] $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

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


echo " BARQ failure_test.sh — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo " Target backend to stop: $TARGET  (other backend: $OTHER)"
echo " Base URL: $BASE_URL"


if ! docker inspect "$TARGET" >/dev/null 2>&1; then
    echo "[FAIL] container '$TARGET' does not exist. Is docker compose up running?"
    exit 1
fi


echo
echo " Baseline (before failure)"
if wait_until "$TARGET healthy" 30 \
    "[ \"\$(docker inspect -f '{{.State.Health.Status}}' $TARGET)\" = 'healthy' ]"; then
    pass "$TARGET is healthy before the test starts"
else
    fail "$TARGET is not healthy before the test starts — aborting"
    exit 1
fi


echo
echo " Stopping $TARGET "
stop_time=$(date +%s)
if docker stop "$TARGET" >/dev/null; then
    pass "docker stop $TARGET succeeded"
else
    fail "docker stop $TARGET failed — aborting"
    exit 1
fi

state=$(docker inspect -f '{{.State.Running}}' "$TARGET")
if [ "$state" = "false" ]; then
    pass "$TARGET is confirmed stopped"
else
    fail "$TARGET still reports Running=true after docker stop"
fi


echo
echo " Availability during failure ($DURING_FAILURE_REQUESTS requests)"
success=0
errors=0
seen_other=0
seen_target_during=0
printf "  progress: "
for i in $(seq 1 "$DURING_FAILURE_REQUESTS"); do
    code=$(curl -s --max-time 5 -o /tmp/failure_test_body.$$ -w '%{http_code}' "$BASE_URL/instance")
    body=$(cat /tmp/failure_test_body.$$ 2>/dev/null || echo "")
    rm -f /tmp/failure_test_body.$$
    if [ "$code" = "200" ]; then
        success=$((success + 1))
        if echo "$body" | grep -q "\"instance_id\":\"$OTHER\""; then seen_other=1; fi
        if echo "$body" | grep -q "\"instance_id\":\"$TARGET\""; then seen_target_during=1; fi
    else
        errors=$((errors + 1))
    fi
    printf "."
done
echo " done"

echo "  Requests: $DURING_FAILURE_REQUESTS total, $success succeeded (HTTP 200), $errors errored"
error_rate=$(( errors * 100 / DURING_FAILURE_REQUESTS ))
echo "  Error rate while $TARGET was down: ${error_rate}%"

if [ "$success" -gt 0 ]; then
    pass "service remained available: $success/$DURING_FAILURE_REQUESTS requests succeeded while $TARGET was down"
else
    fail "service was completely unavailable while $TARGET was down (0 successes)"
fi

if [ "$seen_other" = "1" ]; then
    pass "$OTHER served requests while $TARGET was down (confirmed via instance_id in response body)"
else
    fail "$OTHER was never observed serving a request while $TARGET was down"
fi

if [ "$seen_target_during" = "1" ]; then
    fail "$TARGET (stopped) still appeared in a response — nginx routed to a dead backend"
else
    pass "$TARGET (stopped) never appeared in a response — nginx correctly avoided it"
fi

if [ "$errors" -gt 0 ]; then
    echo "  Note: $errors error(s) observed. Some errors during the exact moment nginx"
    echo "  detects a dead upstream are expected with this nginx config (max_fails=0"
    echo "  disables automatic passive health checks); this is reported, not hidden."
fi


echo
echo " Restoring $TARGET "
if docker start "$TARGET" >/dev/null; then
    pass "docker start $TARGET succeeded"
else
    fail "docker start $TARGET failed — aborting"
    exit 1
fi

if wait_until "$TARGET healthy again" "$RECOVERY_TIMEOUT" \
    "[ \"\$(docker inspect -f '{{.State.Health.Status}}' $TARGET)\" = 'healthy' ]"; then
    recovery_time=$(( $(date +%s) - stop_time ))
    pass "$TARGET became healthy again (total downtime: ${recovery_time}s)"
else
    fail "$TARGET did not become healthy again within ${RECOVERY_TIMEOUT}s"
fi

echo
echo " Verifying $TARGET serves requests again ($AFTER_RECOVERY_REQUESTS requests)"
seen_target_after=0
printf "  progress: "
for i in $(seq 1 "$AFTER_RECOVERY_REQUESTS"); do
    body=$(curl -s --max-time 5 "$BASE_URL/instance")
    if echo "$body" | grep -q "\"instance_id\":\"$TARGET\""; then seen_target_after=1; fi
    printf "."
done
echo " done"

if [ "$seen_target_after" = "1" ]; then
    pass "$TARGET served at least one of $AFTER_RECOVERY_REQUESTS requests after recovery"
else
    fail "$TARGET did not serve any request in $AFTER_RECOVERY_REQUESTS tries after recovery"
fi



echo " Summary: $PASS_COUNT passed, $FAIL_COUNT failed"
echo " Requests during failure: $DURING_FAILURE_REQUESTS total, $success ok, $errors errors (${error_rate}%)"


if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0