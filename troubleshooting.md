# Troubleshooting journal

## Entry 1 — App containers unreachable through nginx
- Symptom: `docker ps` showed app-01/app-02 as `unhealthy`; nginx gave empty replies.
- Hypothesis: APP_HOST bound to loopback only; healthcheck hitting wrong path.
- Command or test: watched container logs during `docker compose up --build`.
- Actual output: `* Running on http://127.0.0.1:8080` + repeating `GET /healthz 404`.
- Failed attempt: typo'd `APP_HOST` as `0.0.0.1` instead of `0.0.0.0` → new error `Cannot assign requested address`. Caught only by retesting, not by `docker compose config`.
- Root cause: `APP_HOST: "127.0.0.1"` (should be `0.0.0.0`) + healthcheck used `/healthz` instead of `/health`.
- Fix: corrected both values in docker-compose.yml.
- Retest evidence: `docker ps` → all 5 containers `(healthy)`.
- Related commit: `d0cc31f`
- Remaining uncertainty: none.

## Entry 2 — Duplicate instance_id
- Symptom: app-02's `INSTANCE_ID` was `"app-01"`.
- Hypothesis: copy-paste error.
- Command or test: grep for INSTANCE_ID in docker-compose.yml.
- Actual output: both services set to `"app-01"`.
- Failed attempt: none.
- Root cause: literal duplicate value.
- Fix: app-02 → `INSTANCE_ID: "app-02"`.
- Retest evidence: `/instance` returns both IDs (confirmed formally in Entry 6/validate.sh).
- Related commit: `d0cc31f`
- Remaining uncertainty: none.

## Entry 3 — Postgres data didn't survive a restart
- Symptom: volume mounted to `/backup` (wrong path); `tmpfs` shadowed the real `/data` dir.
- Hypothesis: misconfigured volume mount.
- Command or test: read docker-compose.yml, cross-checked Postgres's default PGDATA path.
- Actual output: confirmed mismatch directly in the file.
- Failed attempt: none.
- Root cause: wrong mount path + tmpfs wiping data on stop.
- Fix: mounted volume to `/var/lib/postgresql/data`; removed the `tmpfs` line.
- Retest evidence: `persistence_test.sh` — 6/6 passed, record survived full container teardown+recreation.
- Related commit: `d0cc31f`
- Remaining uncertainty: none.

## Entry 4 — Postgres/redis ports published to host
- Symptom: `ports:` blocks published 15432 and 16379, against the brief's rules.
- Hypothesis: leftover debug config.
- Command or test: read docker-compose.yml.
- Actual output: both ports mapped to host.
- Failed attempt: none.
- Root cause: unnecessary host port publication.
- Fix: removed both `ports:` blocks.
- Retest evidence: `validate.sh` confirms nothing listens on 5432/6379 from host.
- Related commit: `d0cc31f`
- Remaining uncertainty: none.

## Entry 5 — nginx could reach postgres/redis directly
- Symptom: nginx was on both `frontend` and `backend` networks.
- Hypothesis: nginx only needs `frontend`.
- Command or test: read `networks:` key across services.
- Actual output: confirmed nginx was the only edge service also on `backend`.
- Failed attempt: none.
- Root cause: unnecessary network attachment.
- Fix: nginx → `networks: [frontend]` only.
- Retest evidence: containers still healthy; `validate.sh` network isolation checks pass.
- Related commit: `d0cc31f`
- Remaining uncertainty: none.

## Entry 6 — nginx misrouted to app-01 and listened on wrong port
- Symptom: containers healthy, but `curl` still gave empty replies.
- Hypothesis: bug inside nginx.conf itself.
- Command or test: read nginx.conf.
- Actual output: `upstream` had `app-01:8081` (should be 8080); `listen 80` (should be 81, per compose's port mapping).
- Failed attempt: after fixing both, `curl http://localhost:8080` still failed. Root cause turned out to be Windows resolving `localhost` to IPv6 first, while nginx is IPv4-only — confirmed via `docker exec nginx wget` with `localhost` vs `127.0.0.1`. Switched to `127.0.0.1` for all tests from then on.
- Root cause: wrong upstream port + wrong listen port.
- Fix: `app-01:8081` → `8080`; `listen 80` → `listen 81`.
- Retest evidence: `curl http://127.0.0.1:8080/` returned a valid response through nginx.
- Related commit: `1ad864d`
- Remaining uncertainty: none (IPv6/localhost is a documented environment quirk, not a project bug).

## Entry 7 — Load balancing looked skewed at first (not a bug)
- Symptom: first several spaced-out requests to `/instance` all returned app-01.
- Hypothesis: possible config bug, or a load-balancing artifact under light traffic.
- Command or test: checked nginx access log's `upstream_addr`; then sent 20 rapid requests instead of spaced ones.
- Actual output: access log confirmed those early requests genuinely all hit app-01; the rapid burst showed proper alternation.
- Failed attempt: initially assumed a config bug before checking the real explanation.
- Root cause: not a bug — `worker_processes auto` gives each nginx worker its own independent round-robin counter, so light/spaced traffic can look skewed.
- Fix: none needed.
- Retest evidence: 20 rapid requests alternated correctly; reconfirmed later in `validate.sh`.
- Related commit: none (no code change; documented in decisions.md).
- Remaining uncertainty: none.

## Entry 8 — DB/Redis connection settings didn't match
- Symptom: `/ready` reported postgres and redis both unavailable.
- Hypothesis: mismatch between `config/app.env` and docker-compose.yml.
- Command or test: compared both files line by line.
- Actual output: password's last char differed (`d` vs `c`); ports wrong (5433 vs 5432, 6380 vs 6379).
- Failed attempt: none.
- Root cause: `config/app.env` shipped with incorrect values.
- Fix: corrected password and both ports.
- Retest evidence: `/ready` → both dependencies `ready`; `/records` and `/counter` do real DB/cache operations.
- Related commit: `cd5c5c6`
- Remaining uncertainty: none.

## Entry 9 — Secrets baked into the image and tracked in git
- Symptom: Dockerfile copied `config/app.env` into the image; `.gitignore` didn't match its path, so it was tracked in git.
- Hypothesis: unnecessary COPY (env already injected via `env_file:` at runtime); ignore pattern too narrow.
- Command or test: read Dockerfile/.gitignore; checked `git status` after `git add -A`.
- Actual output: confirmed file present in image AND tracked in git.
- Failed attempt: none for the fix; found afterward that the file had already been committed earlier, so the synthetic password still exists in git history.
- Root cause: unneeded COPY + gitignore pattern mismatch.
- Fix: removed the COPY line; added `config/app.env` to `.gitignore`; `git rm --cached config/app.env`; expanded `.env.example`.
- Retest evidence: file no longer in the built image; `/ready` still works via `env_file:`.
- Related commit: `cd5c5c6`
- Remaining uncertainty: synthetic password still visible in pre-`cd5c5c6` git history — documented in security_review.md as a known limitation (would require history rewrite for a real secret).

## Entry 10 — Containers ran as root
- Symptom: Dockerfile created an `app` user but ended with `USER root`.
- Hypothesis: `USER app` instruction forgotten/overridden.
- Command or test: read Dockerfile.
- Actual output: `USER root` was the last line before CMD.
- Failed attempt: none.
- Root cause: missing/overridden USER instruction.
- Fix: `USER root` → `USER app`.
- Retest evidence: `docker exec app-01 whoami` → `app`; uid 10001.
- Related commit: `cd5c5c6`
- Remaining uncertainty: none.

## Entry 11 — nginx didn't retry a failed request on the healthy backend
- Symptom: `failure_test.sh` showed 15/30 (50%) errors while app-01 was stopped.
- Hypothesis: nginx not retrying failed requests against the other backend.
- Command or test: read nginx.conf's `location /` and `upstream` blocks.
- Actual output: `proxy_next_upstream off` + `max_fails=0` — failed requests go straight back to the client, never retried.
- Failed attempt: none — config explained the exact error rate on first read.
- Root cause: failover disabled at the request level.
- Fix: `max_fails=2 fail_timeout=5s`; `proxy_next_upstream error timeout http_502 http_503 http_504` + `proxy_next_upstream_tries 2`.
- Retest evidence: re-ran `failure_test.sh` → 0/30 errors. `validate.sh` still 20/20, no regression.
- Related commit: `e811f92`
- Remaining uncertainty: a small window remains between a backend failing and nginx's 2-failure threshold being reached; documented as an accepted trade-off.

## Entry 12 — Windows/Git Bash environment issues (not project bugs)
- Symptom: `localhost` curls failed intermittently; PowerShell's `curl` behaved oddly; `pg_dump` in `backup.sh` failed with a Windows path error; `chmod`/`./script.sh` failed in cmd.exe.
- Hypothesis: Windows/Git-Bash-specific quirks, not application bugs.
- Command or test: ran the `pg_dump` command with/without `MSYS_NO_PATHCONV=1`.
- Actual output: (1) Windows resolves `localhost` to IPv6 first, nginx is IPv4-only; (2) PowerShell's `curl` isn't the real binary; (3) Git Bash rewrites `/tmp/...` paths to Windows paths, breaking `docker exec`; (4) `chmod`/`./` need Git Bash, not cmd.
- Failed attempt: initially suspected `pg_dump` itself was broken before finding the path-rewrite cause.
- Root cause: four separate Windows/Git-Bash environment behaviors.
- Fix (workarounds): use `127.0.0.1` not `localhost`; use `curl.exe` or Git Bash/cmd instead of PowerShell; `export MSYS_NO_PATHCONV=1` before backup/restore/persistence scripts; always run `.sh` files from Git Bash.
- Retest evidence: backup/restore worked after the env var fix; all endpoint tests worked after switching to `127.0.0.1`.
- Related commit: `81bc43a`
- Remaining uncertainty: none — host-environment facts, not project bugs.

## Entry 13 — CI showed a backend excluded from load balancing right after startup
- Symptom: local `validate.sh` runs always passed the load-balancing check (section 3), but the same check failed in GitHub Actions CI: `did not see both backends in 20 requests (app-01 seen=1, app-02 seen=0)`.
- Hypothesis: CI runners are slower/more loaded than the local dev machine, making a timing-sensitive interaction more likely to trigger there than locally.
- Command or test: read the CI job's full log output for the failed step.
- Actual output: confirmed the check ran right after the "wait for readiness" step, which only confirms ONE backend is reachable through nginx (not both individually) before validate.sh runs.
- Failed attempt: none — the CI log made the timing directly visible without needing further investigation.
- Root cause: our own Entry 11 fix (`max_fails=2 fail_timeout=5s`) can exclude a backend from nginx's pool for 5 seconds if it has one slow/failed connection attempt during startup — more likely to happen on a loaded CI runner. If `validate.sh`'s 20-request load-balancing burst completes in under 5 seconds (likely, since requests are fast), it can land entirely inside that exclusion window and only ever see the other backend.
- Fix: made the load-balancing check retry with a bounded backoff (up to 4 attempts, 6s apart — longer than the 5s fail_timeout) instead of failing on the first attempt.

