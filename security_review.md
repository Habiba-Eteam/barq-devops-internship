# Security and production-readiness review

Record at least 8 concrete risks or improvements relevant to your final solution.
This is a review requirement, not the number of hidden faults.

## Finding 1 — Secrets: synthetic credential remains in git history
- Risk and evidence: `config/app.env` (containing a synthetic DB password) was committed once before being untracked. Confirmed still visible via `git log -p` on the earlier commit.
- Impact: if this were a real credential (it isn't — it's fabricated lab data, `BarqLabOnly_...`), anyone with repo access could recover it from history even after removal.
- Implemented fix / commit: `cd5c5c6` — removed from the Dockerfile's `COPY`, added to `.gitignore`, `git rm --cached`. History itself was not rewritten (see production follow-up).
- Production follow-up: for a real secret, immediate credential rotation plus a git history rewrite (`git filter-repo`/BFG) — not optional, and not just untracking the file going forward.
- How to verify: `git log -p -- config/app.env` still shows the value in the pre-`cd5c5c6` commit; `git show HEAD:config/app.env` (current tip) fails since the file is no longer tracked.

## Finding 2 — Ports: postgres/redis were published to the host
- Risk and evidence: baseline `docker-compose.yml` had `ports: ["127.0.0.1:15432:5432"]` and `["127.0.0.1:16379:6379"]`.
- Impact: any process on the host (not just containers on the internal network) could connect directly to the database/cache, bypassing the app layer entirely.
- Implemented fix / commit: `d0cc31f` — removed both `ports:` blocks.
- Production follow-up: none needed for this specific fix; recommend a permanent CI gate (already in place — see verify) so it can't silently regress.
- How to verify: `validate.sh` section 6 — TCP probe confirms nothing listens on `127.0.0.1:5432`/`127.0.0.1:6379`; this check also runs automatically in `ci.yml` on every push.

## Finding 3 — Container user: containers ran as root
- Risk and evidence: `Dockerfile` created a dedicated `app` user (`useradd --uid 10001 ...`) but ended with `USER root`, so every container actually ran as root despite the setup.
- Impact: a container-breakout vulnerability would hand an attacker root inside (and potentially outside, depending on the vulnerability) the container, instead of an unprivileged uid.
- Implemented fix / commit: `cd5c5c6` — `USER root` → `USER app`.
- Production follow-up: the official `nginx`/`postgres`/`redis` images still run their master/entry processes as root by default (standard for those images). Consider `nginx-unprivileged` and reviewing postgres/redis hardening guides (read-only root filesystem, dropped Linux capabilities) for further lockdown.
- How to verify: `docker exec app-01 whoami` → `app`; `docker exec app-01 id` → `uid=10001(app) gid=10001(app)`.

## Finding 4 — Image selection: pinned by digest, but will accumulate CVEs over time
- Risk and evidence: all base images (`python:3.12-slim-bookworm`, `postgres:16-alpine`, `redis:7.4-alpine`, `nginx:1.28-alpine`) are pinned by SHA-256 digest. A Trivy scan runs in CI but is informational only (`exit-code: '0'`).
- Impact: reproducible builds (good), but a pinned digest never auto-updates even after a CVE fix ships upstream, and the current scan configuration can't block a vulnerable build from merging.
- Implemented fix / commit: digest pinning was already present in the baseline; Trivy scan added in `d3cd0fe`/`5e8f93e`.
- Production follow-up: switch the scan to `exit-code: '1'` with an agreed CRITICAL/HIGH threshold, and add a scheduled job to check for newer digests periodically.
- How to verify: `.github/workflows/ci.yml` `security-scan` job output in the Actions tab shows the Trivy report for every run.


## Finding 5 — Availability: single Docker host is a single point of failure
- Risk and evidence: everything (nginx, both app replicas, postgres, redis) runs on one Docker host. postgres specifically has exactly one instance with no replica, even though the app tier has two replicas behind nginx.
- Impact: two app replicas tolerate *one backend* going down (proven by `failure_test.sh` — 0/30 errors when app-01 is stopped), but if the host itself fails, everything goes down together, and there is no way to recover postgres's data without restoring the most recent backup — there is no live standby.
- Implemented fix / commit: `43fd00d` (restart policies + resource limits) reduces the blast radius of a single *container* crash, but does nothing for a whole-host failure — that's explicitly out of scope for a single-host Docker Compose setup.
- Production follow-up: multi-host orchestration (Kubernetes/ECS/Swarm) so app replicas survive a single node failure, and a managed or replicated Postgres (primary + standby, or a managed database service with automated failover) so the data tier isn't a single point of failure either.
- How to verify: not verifiable in this environment by design — this finding documents a structural limitation of a single-host Compose setup, not something `validate.sh`/`failure_test.sh` can exercise (they test container-level failure, not host-level failure).