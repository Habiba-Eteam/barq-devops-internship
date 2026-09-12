# Evidence and submission index

- Repository URL: https://github.com/Habiba-Eteam/barq-devops-internship
- Final commit: `[FINAL COMMIT HASH — fill in after video commits are pushed]`
- Matching CI run: `[Actions run URL for the final commit]`
- Continuous 12-18 minute video URL: `[video URL]`
- Challenge receipt ID: `[from .assessment/challenge.json after running video_challenge.sh]`
- Starting video commit: `[commit hash at the moment recording starts]`
- Later documentation-only commits, if any: `[list any post-video doc-only commits here, e.g. this file itself]`

For each requirement, link: file/output -> commit -> video timestamp.
Match the final README, diagram, GitHub code and video (three instances, public port 8090).

| Requirement | File / output | Commit | Video timestamp |
|---|---|---|---|
| Baseline import, unmodified | full repo at first commit | `84ec8d1` | `[TIMESTAMP]` |
| App binding fix (APP_HOST) | `docker-compose.yml` | `d0cc31f` | — |
| Healthcheck path fix | `docker-compose.yml` | `d0cc31f` | — |
| Distinct instance IDs | `docker-compose.yml` | `d0cc31f` | `[TIMESTAMP]` (`/instance` demo) |
| PostgreSQL named volume, correct mount path | `docker-compose.yml` | `d0cc31f` | `[TIMESTAMP]` (persistence demo) |
| No published postgres/redis host ports | `docker-compose.yml` | `d0cc31f` | `[TIMESTAMP]` (`validate.sh` network section) |
| nginx removed from backend network | `docker-compose.yml` | `d0cc31f` | — |
| nginx upstream port + listen port fix | `nginx/nginx.conf` | `1ad864d` | `[TIMESTAMP]` |
| DB/Redis connection settings fixed | `config/app.env` | `cd5c5c6` | `[TIMESTAMP]` (`/ready` demo) |
| Secrets removed from image + git tracking | `Dockerfile`, `.gitignore`, `.env.example` | `cd5c5c6` | — |
| Non-root container user | `Dockerfile` | `cd5c5c6` | — |
| Restart policies + resource limits | `docker-compose.yml` | `43fd00d` | `[TIMESTAMP]` (`docker inspect` demo) |
| `validate.sh` (Part 3 validation) | `validate.sh` | `e1a48f9` (+ later CI-timing fix) | `[TIMESTAMP]` |
| `failure_test.sh` + nginx failover fix | `failure_test.sh`, `nginx/nginx.conf` | `e811f92` | `[TIMESTAMP]` |
| `backup.sh` / `restore.sh` | `backup.sh`, `restore.sh` | `81bc43a` | `[TIMESTAMP]` |
| `persistence_test.sh` | `persistence_test.sh` | `81bc43a` | `[TIMESTAMP]` |
| CI workflow | `.github/workflows/ci.yml` | `d3cd0fe`, `5e8f93e` | — (see Actions tab) |
| CI security scan (extra credit) | `.github/workflows/ci.yml` | `5e8f93e` | — (see Actions tab) |
| `troubleshooting.md` | `troubleshooting.md` | `[commit hash — check git log]` | — |
| `decisions.md` | `decisions.md` | `[commit hash — check git log]` | — |
| `security_review.md` | `security_review.md` | `[commit hash — check git log]` | — |
| `AI_USAGE.md` | `AI_USAGE.md` | `[commit hash — check git log]` | — |
| `README.md` | `README.md` | `[commit hash — check git log]` | — |
| `architecture.png` (final state) | `architecture.png` | `[commit hash — check git log]` | — |
| `log_analysis.md` + `scripts/analyze_logs.py` | `log_analysis.md`, `scripts/analyze_logs.py` | `[commit hash]` | `[TIMESTAMP]` |
| Live: repo, starting commit, clean `git status` | — | — | `[TIMESTAMP]` |
| Live: build/start stopped environment, show health | — | — | `[TIMESTAMP]` |
| Live: test `/`, `/health`, `/ready`, `/records`, `/counter` | — | — | `[TIMESTAMP]` |
| Live: `/instance` proves both backends serve via nginx | — | — | `[TIMESTAMP]` |
| Live: stop one backend, show continued traffic + errors | — | — | `[TIMESTAMP]` |
| Live: restore backend, prove it serves again | — | — | `[TIMESTAMP]` |
| Live: record survives app+postgres container recreation | — | — | `[TIMESTAMP]` |
| Live: run `validate.sh` and `failure_test.sh` | — | — | `[TIMESTAMP]` |
| Live: demonstrate one historical-log finding | `log_analysis.md` | — | `[TIMESTAMP]` |
| Live: run `video_challenge.sh` (first time, this copy) | `.assessment/challenge.json` | — | `[TIMESTAMP]` |
| Live: diagnose + fix the challenge's runtime fault | — | `[commit hash]` | `[TIMESTAMP]` |
| Live: change public port 8080 -> 8090 | `docker-compose.yml` | `[commit hash]` | `[TIMESTAMP]` |
| Live: add third app instance (app-03) | `docker-compose.yml` | `[commit hash]` | `[TIMESTAMP]` |
| Live: rerun validation with 3 instances | — | — | `[TIMESTAMP]` |
| Live: `git status` / `git diff`, explain + commit on screen | — | `[commit hash]` | `[TIMESTAMP]` |
| Live: push video commits | — | — | `[TIMESTAMP]` |

## Notes

- Commit hashes for documentation files need to be filled in from a fresh
  `git log --oneline` before final submission — several docs were committed
  after this table was first drafted.
- All `[TIMESTAMP]` placeholders are filled in immediately after recording,
  using the video's actual elapsed time.
- Rows marked `—` for video timestamp were fixed and verified before
  recording (evidenced by commit + retest evidence in `troubleshooting.md`),
  not necessarily re-demonstrated live, unless the brief specifically
  requires a live demonstration.