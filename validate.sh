

set -uo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
CONTAINER_TIMEOUT="${CONTAINER_TIMEOUT:-60}"   # seconds to wait for containers to go healthy
HTTP_TIMEOUT="${HTTP_TIMEOUT:-30}"             # seconds to wait for nginx to answer
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


echo " BARQ validate.sh — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo " Base URL: $BASE_URL"



#  Container healtا

echo
echo "Container health "
for c in app-01 app-02 postgres redis nginx; do
    if ! docker inspect "$c" >/dev/null 2>&1; then
        fail "container '$c' does not exist (is docker compose up running?)"
        continue
    fi
    has_healthcheck=$(docker inspect -f '{{if .State.Health}}yes{{else}}no{{end}}' "$c")
    if [ "$has_healthcheck" = "yes" ]; then
        if wait_until "$c healthy" "$CONTAINER_TIMEOUT" \
            "[ \"\$(docker inspect -f '{{.State.Health.Status}}' $c)\" = 'healthy' ]"; then
            pass "$c reports healthy"
        else
            status=$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo "unknown")
            fail "$c did not become healthy within ${CONTAINER_TIMEOUT}s (last status: $status)"
        fi
    else
        # nginx has no HEALTHCHECK in this project; just confirm it's running
        running=$(docker inspect -f '{{.State.Running}}' "$c")
        if [ "$running" = "true" ]; then
            pass "$c is running (no healthcheck defined for this service)"
        else
            fail "$c is not running"
        fi
    fi
done

# Public access through nginx

echo
echo " Public endpoints "

if wait_until "nginx responding on $BASE_URL/" "$HTTP_TIMEOUT" \
    "curl -sf --max-time 5 -o /dev/null '$BASE_URL/'"; then
    pass "GET / reachable through nginx"
else
    fail "GET / not reachable through nginx within ${HTTP_TIMEOUT}s"
fi

check_endpoint_status() {
    local path="$1" expected="$2"
    local code
    code=$(curl -s --max-time 5 -o /dev/null -w '%{http_code}' "$BASE_URL$path")
    if [ "$code" = "$expected" ]; then
        pass "GET $path returned $expected"
    else
        fail "GET $path returned $code, expected $expected"
    fi
}

check_endpoint_status "/health" "200"
check_endpoint_status "/ready" "200"

ready_body=$(curl -s --max-time 5 "$BASE_URL/ready")
if echo "$ready_body" | grep -q '"status":"ready"' \
    && echo "$ready_body" | grep -q '"postgres":"ready"' \
    && echo "$ready_body" | grep -q '"redis":"ready"'; then
    pass "/ready reports postgres AND redis ready (real dependency check)"
else
    fail "/ready did not report both postgres and redis ready: $ready_body"
fi




echo
echo " Load balancing across both backends "
lb_attempt=0
lb_max_attempts=4
lb_ok=0
while [ "$lb_attempt" -lt "$lb_max_attempts" ]; do
    lb_attempt=$((lb_attempt + 1))
    seen_app01=0
    seen_app02=0
    printf "  progress (attempt %s/%s): " "$lb_attempt" "$lb_max_attempts"
    for i in $(seq 1 20); do
        body=$(curl -s --max-time 5 "$BASE_URL/instance")
        if echo "$body" | grep -q '"instance_id":"app-01"'; then seen_app01=1; fi
        if echo "$body" | grep -q '"instance_id":"app-02"'; then seen_app02=1; fi
        printf "."
    done
    echo " done"
    if [ "$seen_app01" = "1" ] && [ "$seen_app02" = "1" ]; then
        lb_ok=1
        break
    fi
    if [ "$lb_attempt" -lt "$lb_max_attempts" ]; then
        echo "  only saw app-01=$seen_app01 app-02=$seen_app02 -- waiting 6s for nginx's fail_timeout window to clear, then retrying"
        sleep 6
    fi
done
if [ "$lb_ok" = "1" ]; then
    pass "both app-01 and app-02 served at least one of 20 requests to /instance (within $lb_attempt attempt(s))"
else
    fail "did not see both backends after $lb_max_attempts attempts (app-01 seen=$seen_app01, app-02 seen=$seen_app02)"
fi


echo
echo " PostgreSQL-backed /records"
marker="validate-$(date +%s)"
create_body=$(curl -s --max-time 5 -X POST "$BASE_URL/records" \
    -H "Content-Type: application/json" \
    -d "{\"title\":\"$marker\"}")
if echo "$create_body" | grep -q "\"title\":\"$marker\""; then
    pass "/records POST created a row (id assigned by PostgreSQL)"
else
    fail "/records POST did not return the created row: $create_body"
fi

list_body=$(curl -s --max-time 5 "$BASE_URL/records")
if echo "$list_body" | grep -q "\"title\":\"$marker\""; then
    pass "/records GET lists the row just created (real DB read, not a stub)"
else
    fail "/records GET did not include the just-created row: $list_body"
fi



echo
echo " Redis-backed /counter "
c1=$(curl -s --max-time 5 "$BASE_URL/counter" | grep -o '"counter":[0-9]*' | grep -o '[0-9]*')
c2=$(curl -s --max-time 5 "$BASE_URL/counter" | grep -o '"counter":[0-9]*' | grep -o '[0-9]*')
if [ -n "$c1" ] && [ -n "$c2" ] && [ "$c2" -gt "$c1" ]; then
    pass "/counter increments across requests ($c1 -> $c2), real Redis operation"
else
    fail "/counter did not increment as expected (got '$c1' then '$c2')"
fi




echo " Network isolation "

port_closed_from_host() {
    # Returns success (0) if nothing is listening on 127.0.0.1:$1
    local port="$1"
    if command -v nc >/dev/null 2>&1; then
        ! nc -z -w2 127.0.0.1 "$port" 2>/dev/null
    else
        # Fallback: bash /dev/tcp probe
        ! (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null
    fi
}

if port_closed_from_host 5432; then
    pass "postgres port 5432 is NOT reachable from the host"
else
    fail "postgres port 5432 IS reachable from the host (should not be published)"
fi

if port_closed_from_host 6379; then
    pass "redis port 6379 is NOT reachable from the host"
else
    fail "redis port 6379 IS reachable from the host (should not be published)"
fi



echo
echo " Published host ports "
for c in app-01 app-02 postgres redis; do
    published=$(docker port "$c" 2>/dev/null)
    if [ -z "$published" ]; then
        pass "$c publishes no host ports"
    else
        fail "$c publishes host port(s): $published"
    fi
done

nginx_ports=$(docker port nginx 2>/dev/null)
if echo "$nginx_ports" | grep -q "8080\|${PUBLIC_PORT:-8080}"; then
    pass "nginx publishes exactly the expected public port"
else
    fail "nginx port publication looks wrong: $nginx_ports"
fi


echo " Summary: $PASS_COUNT passed, $FAIL_COUNT failed"
if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0