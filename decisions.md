# Technical decisions

Record at least 5 decisions. Include assumptions and limits.

## Decision — base image
- Choice: `python:3.12-slim-bookworm`, pinned by digest (`@sha256:...`), kept as-is from the starter pack.
- Why: `slim` keeps the image small while still being a full Debian userland (unlike `alpine`, which uses musl libc and can cause subtle issues with some Python C-extension wheels like `psycopg[binary]`). Digest pinning means the exact same bytes get pulled every build, not just the same tag.
- Alternative: `python:3.12-alpine` (smaller, but higher risk of wheel-compatibility issues); `python:3.12` full image (larger, more OS packages than needed).
- Trade-off: `slim-bookworm` is bigger than alpine but avoids musl-related build/runtime surprises with `psycopg-binary`.
- Evidence / commit: unchanged from baseline — `Dockerfile` line 1.
- Production improvement: consider a distroless or multi-stage build to strip pip/build tooling out of the final image and shrink the attack surface further.

## Decision — health check tool
- Choice: kept the existing healthcheck approach — `python -c "import urllib.request; ..."` for app-01/app-02, `pg_isready` for postgres, `redis-cli ping` for redis. No `curl`/`wget` installed in the app image.
- Why: the app image already has Python (it's the runtime), so using `urllib.request` needs no extra package install; `pg_isready`/`redis-cli` ship inside their respective official images already.
- Alternative: install `curl` in the app image and use `curl -f http://127.0.0.1:8080/health` (more common convention, but adds an unnecessary package to a minimal image just for the healthcheck).
- Trade-off: the Python one-liner is slightly less readable than a plain `curl` command, but avoids installing anything extra.
- Evidence / commit: `d0cc31f` (path fixed from `/healthz` to `/health`; tool choice itself was already correct in the baseline).
- Production improvement: none needed — this is a reasonable, minimal-dependency choice for a Python-based image.

## Decision — network topology (frontend/backend split)
- Choice: two networks — `frontend` (nginx + app-01 + app-02) and `backend` (app-01 + app-02 + postgres + redis, `internal: true`). nginx is frontend-only.
- Why: `internal: true` on `backend` means that network has no route to the outside world at all — even if someone misconfigured a port publish on postgres/redis again, `backend` itself provides a second layer of isolation. nginx being frontend-only enforces "nginx can reach the apps, never the data layer" at the network level, not just by convention.
- Alternative: one flat network for everything (simpler, but no isolation between the edge and the data layer — exactly the Entry 5 bug found and fixed).
- Trade-off: two networks add a small amount of compose-file complexity in exchange for defense-in-depth.
- Evidence / commit: `d0cc31f` (nginx removed from `backend`); `validate.sh` network isolation checks.
- Production improvement: in a real cloud deployment, this maps naturally to separate subnets/security groups with the same edge/data separation.

## Decision — restart policy: `on-failure:5`, not `always`
- Choice: all services use `restart: on-failure:5`.
- Why: Part 3's `failure_test.sh` needs to manually `docker stop` a backend and observe it stay down while measuring traffic/errors, before manually restoring it. `on-failure` only restarts on a genuine crash (non-zero exit), not a clean manual stop (exit code 0) — `always` would fight that test.
- Alternative: `always` or `unless-stopped` (restart on any stop, including manual); `no` (never restart, the original baseline).
- Trade-off: a container someone stops by mistake in production stays down until something else notices and restarts it — real orchestration (k8s, ECS, swarm) would be needed for that, not just this restart policy.
- Evidence / commit: `43fd00d`; verified via `docker inspect --format '{{.HostConfig.RestartPolicy.Name}}'` → `on-failure`.
- Production improvement: pair with an external health-based orchestrator/monitor for unattended recovery beyond 5 retries.

## Decision — resource limits sized per service, not uniform
- Choice: `nginx`/`redis` get lightweight limits (64–128MB), `app-01`/`app-02`/`postgres` get more (256–512MB), each with a 0.25–0.5 CPU cap.
- Why: matches each service's actual footprint — nginx and redis are lightweight processes, postgres and the Flask apps need more headroom.
- Alternative: one uniform limit for every service (simpler, but wastes memory on nginx/redis or risks starving postgres); no limits at all (the baseline — rejected since it's required and unbounded containers can starve the host).
- Trade-off: values were chosen to comfortably pass this project's test suite, not benchmarked against real production load.
- Evidence / commit: `43fd00d`; verified via `docker inspect --format '{{.HostConfig.Memory}}'` → exact byte values matching the configured limits.
- Production improvement: load-test with realistic traffic and tune limits from real metrics rather than estimates.

## Decision — nginx failover: retry once, mark a backend down after 2 failures
- Choice: `max_fails=2 fail_timeout=5s` per upstream server; `proxy_next_upstream error timeout http_502 http_503 http_504` with `proxy_next_upstream_tries 2`.
- Why: `failure_test.sh` measured a 50% client-facing error rate with the baseline (`proxy_next_upstream off`, `max_fails=0`) while one backend was down. This config makes nginx retry a failed request against the other backend instead of returning the error straight to the client, and temporarily stop routing to a backend after 2 failures.
- Alternative: leave `proxy_next_upstream off` (the baseline — rejected on measured evidence); `max_fails=1` (more aggressive, risks flapping a backend down from a single transient blip).
- Trade-off: still a small window (up to 2 failed requests) between a backend dying and nginx marking it down — not a guaranteed zero-error failover, but bounded instead of unbounded.
- Evidence / commit: `e811f92`; `failure_test.sh` re-run after the fix showed 0/30 errors (was 15/30 before).
- Production improvement: nginx open-source has no active health checks (only passive, request-driven ones like this). nginx Plus or an external health-checking load balancer would close the remaining gap, especially for backends that hang instead of refusing connections.

## Decision — storage: named volume for postgres, no persistence for redis
- Choice: `postgres-data` named volume mounted at `/var/lib/postgresql/data` (persistent across restarts); redis runs with `--save "" --appendonly no` (no persistence — an in-memory cache that resets on restart).
- Why: `/records` needs durable storage (real user data via PostgreSQL), matching the brief's requirement to prove a record survives container recreation. `/counter` is presented as a lightweight demo counter, not data anyone depends on surviving a restart, so redis staying pure in-memory is an acceptable, explicit choice rather than an oversight.
- Alternative: also enable redis persistence (RDB snapshots or AOF) so `/counter` survives restarts too.
- Trade-off: simpler, faster redis (no disk I/O) in exchange for the counter resetting to 0 on every `docker compose down`/`up`.
- Evidence / commit: postgres volume fix in `d0cc31f`; proven via `persistence_test.sh` (6/6 passed — record survived full teardown+recreation).
- Production improvement: if the counter (or any future redis-backed feature) needs to survive restarts, enable AOF (`--appendonly yes`) and mount a named volume for redis too, same pattern as postgres.

## Decision — kept a pre-existing synthetic secret in git history rather than rewriting it
- Choice: `config/app.env` was untracked going forward (`git rm --cached` + `.gitignore`), but the earlier commit that originally added it was left in git history as-is.
- Why: the value is fabricated lab data (`BarqLabOnly_...`), explicitly not a real credential per the brief's own rules — it carries no real-world risk sitting in old commits.
- Alternative: `git filter-repo`/BFG to purge it from all history — technically possible, but rewrites every downstream commit hash, risking the graded commit trail this assessment explicitly wants intact.
- Trade-off: accepted a known, harmless trace in history in exchange for not disturbing the commit trail.
- Evidence / commit: `cd5c5c6`; documented as a named risk in `security_review.md`.
- Production improvement: if this were ever a real credential, the correct response is immediate rotation of the credential plus a history rewrite — not just untracking the file going forward.

## Decision — CI security scan is informational, not a blocking gate
- Choice: the `security-scan` CI job runs Trivy against the built image with `exit-code: '0'` — findings are visible in the Actions log but don't fail the pipeline.
- Why: for this assessment, demonstrating the scan runs correctly matters more than gating every push on a clean result, especially since the base image will always carry some CVEs no amount of app-level work can remove.
- Alternative: `exit-code: '1'` with a severity threshold (CRITICAL/HIGH) — the stricter, more production-appropriate setting.
- Trade-off: nothing currently stops a vulnerable image from being built and used based on CI status alone; a human has to read the scan output.
- Evidence / commit: `d3cd0fe` / `5e8f93e`; visible in the Actions run.
- Production improvement: switch to `exit-code: '1'` with an agreed severity threshold and a documented exception process for accepted-risk CVEs.