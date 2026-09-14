# Log analysis

Use all three supplied logs. Answer every question with commands/scripts and actual output.

All numbers below come from `python3 scripts/analyze_logs.py`, run from the
repo root. Full output saved at `scripts/last_run_output.txt`. Original log
files under `logs/` were never modified.

## 1. What UTC interval is covered? How many valid, malformed and duplicate lines are in each file?

**Interval covered:** `2026-08-20T11:00:00.015Z` to `2026-08-20T11:29:57.578Z` (~30 minutes).

| File | Raw lines | Valid (parsed) | Malformed (excluded) | Duplicate (removed) | Unique kept |
|---|---|---|---|---|---|
| access.log | 725 | 724 | 1 (line 311, truncated JSON) | 4 exact-duplicate lines | 720 |
| application.log | 729 | 728 | 1 (line 401, truncated JSON) | 2 exact-duplicate lines | 727 |
| error.log | 68 | 67 | 1 (line 68, doesn't match the expected nginx error format) | 0 | 67 |

Malformed lines are excluded, not repaired or guessed at, per `logs/README.md`.

## 2. How many distinct client requests occurred? How did you deduplicate and avoid counting retries twice?

**720 distinct client requests** (access.log, post-deduplication).

Deduplication removed only byte-identical repeated lines (e.g. `lab-000121`
appears twice at the exact same timestamp — a logging/probe artifact, not two
real client requests).

Retries are **not** double-counted, and needed no special handling: nginx
writes exactly **one** access.log line per client request even when it
retries against a second upstream internally — the `upstream` and
`upstream_status` fields become comma-separated lists describing each attempt
within that single line (see Q6 for a concrete example). Counting access.log
lines (post-dedup) therefore already equals counting distinct client
requests; no additional collapsing by request_id was needed for this file.

(application.log needed different handling — see the note in the reproduce
section at the bottom: some request_ids there legitimately carry two
different event types, `http_request` and `dependency_error`, which are not
duplicates and were both kept.)

## 3. What are the final client status counts and error rate? State your denominator.

**Denominator: 720** (distinct client requests, access.log, post-dedup).

| Status | Count | % of total |
|---|---|---|
| 200 | 615 | 85.4% |
| 404 | 10 | 1.4% |
| 502 | 40 | 5.6% |
| 503 | 47 | 6.5% |
| 504 | 8 | 1.1% |

- **Server error rate (5xx only): 95/720 = 13.19%**
- All non-2xx rate (4xx+5xx, includes the 404s): 105/720 = 14.58%

The 5xx figure is the more meaningful "error rate" for an incident review —
the 404s are ordinary client requests to a non-existent resource, not a
service failure.

## 4. Which paths, time windows and backends account for the failures?

**By path (5xx failures only, n=95):**

| Path | Failures |
|---|---|
| `/records` | 26 |
| `/counter` | 26 |
| `/ready` | 23 |
| `/health` | 10 |
| `/` | 10 |

No single path dominates — failures are spread across nearly every endpoint,
consistent with an infrastructure-level outage rather than a bug in one
specific route.

**By first-attempted backend:**

| Backend | Failures (first attempt) |
|---|---|
| `172.23.0.12:8080` | 68 |
| `172.23.0.11:8080` | 27 |

`172.23.0.12` (app-02) accounts for the large majority — consistent with
Q7's finding that app-02 was the unreachable instance for most of the
incident.

**By time window** (5-minute buckets, non-2xx responses in access.log):

| Window (UTC) | Non-2xx count |
|---|---|
| 11:00 | 2 |
| 11:05 | 42 |
| 11:10 | 24 |
| 11:15 | 10 |
| 11:20 | 17 |
| 11:25 | 10 |

Two distinct spikes: one at 11:05 (connect-refused outage starting) and a
second, broader elevated period from 11:10–11:20 (the separate dependency
incident — see Q7/Q9).

## 5. What are the median and p95 client latencies? State the percentile method and units.

Using `request_time` from access.log (seconds per `logs/README.md`; converted
to milliseconds below), n=720, **linear interpolation between closest ranks**
(the standard/numpy-style percentile method):

- **Median (p50): 54.0 ms**
- **p95: 2001.0 ms**

The large gap between median and p95 is expected here: the bulk of traffic is
fast (median 54ms), but a small tail of requests during the incident window
hit nginx's `proxy_connect_timeout`/`proxy_read_timeout` (2s/3s) while
waiting on a dead or slow backend, pulling p95 up to ~2 seconds.

## 6. Which requests retried upstream? How many succeeded after retrying?

**19 requests** show more than one upstream attempt (comma-separated
`upstream`/`upstream_status` fields in access.log) — nginx retried these
against a second backend after the first attempt failed.

- **19/19 succeeded after retry** (final status 200 in every case) — 0 still
  failed after retrying.

Example:
request_id=lab-000124
upstream: "172.23.0.12:8080, 172.23.0.11:8080"
upstream_status: "502, 200"
final status: 200


This shows nginx tried app-02 first (502, connection refused), then
immediately retried app-01 (200) — the client never saw the failure.

**Note on retries vs. Incident A's raw error count:** 67 error.log
connect-refused events occurred, but only 40 access.log requests ended in a
502 — the other 19 of these attempts were saved by a retry (see above) and
the remaining ~8 map to other failure paths (504s, or requests where nginx
had already exhausted its retry budget). This is why "connect-refused count"
and "client-visible failure count" are different numbers, and why stating a
denominator (Q3) matters.

## 7. Build an incident timeline using evidence from access, error AND application logs.

| Time (UTC) | Source | Evidence |
|---|---|---|
| 11:00:00 | access.log | Normal traffic begins, ~2 non-2xx in this window (baseline noise) |
| **11:05:02** | error.log | First `connect() failed (111: Connection refused)` to `172.23.0.12:8080` (app-02) — **Incident A starts** |
| 11:05:02–11:09:59 | error.log + access.log | 59 connect-refused events in this window; access.log shows a matching spike to 42 non-2xx responses; some recover via retry (Q6) |
| 11:05:xx–11:26:xx | application.log | `instance_id` distribution during this window: app-01=302, app-02=226 (vs. a near-even 100/99 split outside it) — app-02 intermittently missing traffic |
| **11:12:09.524** | application.log | First `dependency_error` event (`redis`/`TimeoutError`) — **Incident B starts, overlapping Incident A** |
| 11:12:09–11:21:45 | application.log | 47 `dependency_error` events total: 31 redis `TimeoutError`, 16 postgres `InvalidPassword`, split almost evenly across app-01 (23) and app-02 (24) — proving Incident B hit *both* instances, unlike Incident A |
| 11:10–11:20 | access.log | Elevated non-2xx (24, then 10, then 17) — the 503s and 504s from Incident B's dependency failures |
| **11:21:45.040** | application.log | Last `dependency_error` event — **Incident B ends** |
| **11:25:00–11:26:47** | error.log | A final burst of 8 connect-refused events, still against `172.23.0.12` — a second, shorter flare-up of Incident A |
| 11:26:47 | error.log | Last connect-refused event — **Incident A ends** |
| 11:29:57 | access.log | Last log entry in the supplied window |

Two distinct, overlapping incidents, not one: Incident A (app-02 unreachable,
connection-level) ran ~11:05–11:26 with a gap in the middle; Incident B
(redis timeouts + postgres auth failures, dependency-level, hitting both
instances) ran ~11:12–11:21, fully nested inside Incident A's window but with
an unrelated root cause.

## 8. Show one correlated failed request and one successful request. Include IDs and timestamps.

**Failed request** (proxy/connectivity failure — Incident A):
request_id: lab-000122
timestamp: 2026-08-20T11:05:02.503Z (access.log) / 11:05:02 (error.log, second precision)
error.log: connect() failed (111: Connection refused) while connecting to
upstream, request: "GET /health HTTP/1.1",
upstream: "http://172.23.0.12:8080/health"
access.log: {"status": 502, "upstream": "172.23.0.12:8080",
"upstream_status": "502", "request_time": 0.003}
application.log: NO MATCHING ENTRY

The missing application.log entry is itself evidence: the app never received
this request — nginx failed before the connection was ever established,
confirming this is a proxy-layer failure, not an application bug.

**Successful request** (normal operation, for contrast):

request_id: lab-000006
timestamp: 2026-08-20T11:00:12.520Z
access.log: {"status": 200, "upstream": "172.23.0.12:8080",
"upstream_status": "200", "request_time": 0.02}
application.log: {"event": "http_request", "instance_id": "app-02",
"status": 200, "duration_ms": 20.0}

Here both logs agree: nginx and the app both saw and completed the same
request in ~20ms, well before either incident began.

## 9. Which errors appear to be proxy/connectivity issues versus dependency/application issues? What proves it?

**Proxy/connectivity (Incident A):** all 67 error.log `connect() failed
(111: Connection refused)` events. Proof: these are logged by nginx itself,
before the app ever sees the request (Q8's failed example has no
application.log counterpart at all) — nginx couldn't even open a TCP
connection to the upstream IP:port it names explicitly.

**Dependency/application (Incident B):** all 47 application.log
`dependency_error` events (redis `TimeoutError`, postgres `InvalidPassword`).
Proof: these are logged by the app itself (`"service": "barq-api"`), which
means the app *did* receive the request and *did* attempt to use the
dependency — the failure happened one layer deeper than the proxy, inside
the app's own dependency calls, and nginx's corresponding access.log line
for these requests shows a normal proxied flow (no connect-refused), just an
eventual 503 returned by the app itself.

## 10. What do the logs not prove? What would you check next in a running environment?

**What the logs don't prove:**
- **Why** app-02 became unreachable (crash? OOM-kill? a bad deploy? a network
  partition?) — the logs show *that* it was unreachable, not the underlying
  cause.
- **Why** the redis/postgres dependency errors happened at the application
  layer — the logs show a `TimeoutError`/`InvalidPassword`, but not, e.g.,
  redis's own server-side state or postgres's own auth log at that moment.
- Whether these two incidents share a common trigger (e.g. a bad deploy or
  config change around 11:05–11:12) or are coincidentally overlapping —
  the logs alone don't establish causality between them, only correlation
  in time.
- Host-level resource pressure (CPU/memory/disk) during either incident —
  none of the three logs capture that.
- Whether any client-side retries happened *above* nginx (i.e., did the
  actual end users/scripts retry a failed request themselves) — these logs
  only show nginx's own internal upstream retries (Q6), not client behavior.

**What to check next in a running environment:**
- `docker events`/container restart history around 11:05 and 11:12, to see
  if app-02 or the dependency layer actually crashed/restarted at those
  times.
- postgres's and redis's own server-side logs for the same window, to
  corroborate the `InvalidPassword`/`TimeoutError` findings from the
  application side.
- Host metrics (CPU, memory, network) for the same window, to rule out
  resource exhaustion as a shared root cause for both incidents.
- Deployment/change history around 11:00–11:12, to check whether a config or
  code change coincided with the start of either incident.

## Commands / scripts

```bash
python3 scripts/analyze_logs.py
```
Run from the repository root. Reads `logs/*.log` only; never modifies the
originals. Full output from the run behind this document is saved at
`scripts/last_run_output.txt`.

## Results

See the numbered answers above (Q1–Q9) — each is backed directly by the
script's output, not manual counting.

## Timeline and correlated examples

See Q7 (timeline) and Q8 (correlated failed/successful request pairs) above.

## Conclusions and limits

Two distinct, time-overlapping incidents occurred in this historical window:
a connectivity failure isolated to app-02 (Incident A, ~11:05–11:26) and a
dependency-layer failure hitting both app instances (Incident B,
~11:12–11:21, redis timeouts + postgres auth failures). Nginx's internal
upstream retry saved 19 requests from becoming client-visible failures
during Incident A. See Q10 for what these logs cannot establish on their own
and what a live investigation would check next.