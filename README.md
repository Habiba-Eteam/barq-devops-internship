# BARQ DevOps Internship — Task Solution

A Flask app running behind NGINX, load-balanced across two instances, backed
by PostgreSQL (persistent) and Redis. This README covers everything needed to
build, run, test, and tear the environment down.

**Windows users:** run all commands below from **Git Bash**, not Command
Prompt or PowerShell (`chmod`, `./script.sh`, and some path handling need it).

## Prerequisites

- Docker Desktop (with Docker Compose v2) installed and running
- Git Bash (Windows) or any POSIX shell (macOS/Linux)

## Setup

```bash
git clone https://github.com/Habiba-Eteam/barq-devops-internship.git
cd barq-devops-internship
cp .env.example .env      # see below — .env itself is optional, PUBLIC_PORT defaults to 8080
```

Create `config/app.env` (gitignored — never committed, see `security_review.md`)
with real values for local development:
```bash
cat > config/app.env <<'EOF'
DATABASE_URL=postgresql://barq_app:BarqLabOnly_7qN2vK8c@postgres:5432/barq_tasks
REDIS_URL=redis://redis:6379/0
EOF
```

## Build and start

```bash
docker compose up --build
```

Wait for all 5 containers to report healthy:
```bash
docker ps
```
You should see `app-01`, `app-02`, `postgres`, `redis` as `(healthy)` and
`nginx` as `Up`.

## Verify it's working

```bash
curl http://127.0.0.1:8080/
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/ready
curl http://127.0.0.1:8080/instance
curl -X POST http://127.0.0.1:8080/records -H "Content-Type: application/json" -d '{"title":"hello"}'
curl http://127.0.0.1:8080/records
curl http://127.0.0.1:8080/counter
```

**Important (Windows):** use `127.0.0.1`, not `localhost` — Windows resolves
`localhost` to IPv6 first, and nginx here is IPv4-only. See `troubleshooting.md`
Entry 6.

## Run the app-only unit tests (fake dependencies, no Docker needed)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## Stop

```bash
docker compose down
```
This removes containers but **keeps** the `postgres-data` volume (data
persists). Add `-v` only if you intentionally want to wipe the database too.

## Run the automated checks

```bash
chmod +x validate.sh failure_test.sh backup.sh restore.sh persistence_test.sh
export MSYS_NO_PATHCONV=1   # Windows/Git Bash only — needed for backup.sh/restore.sh

./validate.sh               # 20 checks: endpoints, load balancing, DB/cache ops, network isolation
./failure_test.sh           # stops app-01, proves the service stays up, restores it
./persistence_test.sh       # proves data survives a full container recreation
./backup.sh                 # writes a PostgreSQL backup to ./backups/
./restore.sh backups/<the file backup.sh just created>
```

Each script prints `[PASS]`/`[FAIL]` per check and exits non-zero if anything
fails.

## Cleanup

```bash
docker compose down -v      # removes containers AND the postgres-data volume
docker image prune -f       # optional: remove dangling build images
rm -rf backups/*.dump       # optional: remove local backup files (gitignored anyway)
```

## Project layout
.
├── app/ # Flask application source
├── tests/ # app-only unit tests (fake dependencies)
├── config/app.env # gitignored — real DB/Redis credentials for local dev
├── database/init.sql # seed schema, run automatically by postgres on first start
├── nginx/nginx.conf # reverse proxy + load balancer config
├── docker-compose.yml
├── Dockerfile
├── validate.sh # Part 3: endpoint/network/LB validation
├── failure_test.sh # Part 3: backend failure + recovery test
├── backup.sh / restore.sh # Part 3: PostgreSQL logical backup/restore
├── persistence_test.sh # Part 3: proves data survives container recreation
├── video_challenge.sh # Part 5: recorded runtime-fault challenge (run once, on video)
├── scripts/analyze_logs.py # Part 1: log analysis (see log_analysis.md)
├── .github/workflows/ci.yml
├── troubleshooting.md # investigation journal
├── decisions.md # technical decisions, trade-offs, alternatives
├── security_review.md # security/production-readiness findings
├── log_analysis.md # Part 1 log analysis writeup
├── AI_USAGE.md # AI usage disclosure
└── docs/ARCHITECTURE.md # architecture diagram + explanation


## CI

Every push/PR to `main` runs `.github/workflows/ci.yml`: builds the images,
starts the stack, waits for readiness, runs `validate.sh` and
`failure_test.sh`, and (as extra credit) scans the app image with Trivy. See
the Actions tab on GitHub for run history.

## Further reading

- `troubleshooting.md` — every issue found, how it was diagnosed, and how it was fixed
- `decisions.md` — why things were built the way they were, including alternatives considered
- `security_review.md` — known risks and what a production deployment would still need
- `log_analysis.md` — analysis of the historical incident logs shipped with the starter pack

---
**Note:** this README reflects the pre-video state (2 app instances, port
8080). Per the task brief, a live third instance and a port change to 8090
happen during the Part 5 video recording — this file gets one final update
immediately afterward to match that final state exactly.