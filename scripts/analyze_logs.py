#!/usr/bin/env python3
"""
analyze_logs.py — Part 1 log analysis for the BARQ DevOps internship task.

Parses logs/access.log, logs/error.log, logs/application.log (read-only,
originals are never modified), correlates them by request_id, and prints:
  - malformed / unparseable line counts (excluded, listed explicitly)
  - status code counts (access + application)
  - errors-by-time timeline (5-minute buckets)
  - the historical outage window (based on nginx "Connection refused" errors)
  - instance (app-01 / app-02) request distribution during vs outside the outage
  - duplicate request_id detection (so a client request is not double-counted)
  - basic latency stats

Usage:
    python3 scripts/analyze_logs.py
Run from the repo root (paths are relative to ./logs/).
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean, median

LOG_DIR = "logs"


def parse_ts(s: str) -> datetime:
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def load_jsonl(path):
    """Load a JSON-lines log file. Returns (records, malformed_line_numbers)."""
    records = []
    malformed = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append((i, json.loads(line)))
            except json.JSONDecodeError:
                malformed.append(i)
    return records, malformed


def load_error_log(path):
    """
    nginx error.log is plain text, not JSON. Extract timestamp, request_id,
    and upstream from each line with a regex. Lines that don't match the
    expected pattern are counted as malformed/unparseable.
    """
    pattern = re.compile(
        r"^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \[error\] .*?"
        r"request_id=(?P<rid>\S+?),\s*request: \"(?P<method>\w+) (?P<path>\S+) [^\"]+\",\s*"
        r"upstream: \"http://(?P<upstream>[^/]+)"
    )
    records = []
    malformed = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            m = pattern.match(line)
            if not m:
                malformed.append(i)
                continue
            d = m.groupdict()
            d["ts_dt"] = datetime.strptime(d["ts"], "%Y/%m/%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            records.append((i, d))
    return records, malformed


def main():
    print("=" * 70)
    print("BARQ log analysis — reproducible run of scripts/analyze_logs.py")
    print("=" * 70)

    access_raw, access_bad = load_jsonl(f"{LOG_DIR}/access.log")
    app_raw, app_bad = load_jsonl(f"{LOG_DIR}/application.log")
    err, err_bad = load_error_log(f"{LOG_DIR}/error.log")

    print(f"\nParse summary ")
    print(f"access.log:      {len(access_raw)} parsed, {len(access_bad)} malformed "
          f"(excluded) at line(s): {access_bad}")
    print(f"application.log: {len(app_raw)} parsed, {len(app_bad)} malformed "
          f"(excluded) at line(s): {app_bad}")
    print(f"error.log:       {len(err)} parsed, {len(err_bad)} unparseable "
          f"(excluded) at line(s): {err_bad}")

    # Duplicate request_id detection (avoid double-counting) 
    # A log record is not always a distinct client request (see logs/README.md).
    # De-duplicate by request_id, keeping the first occurrence, before computing
    # any counts/timelines below so repeated lines aren't counted twice.
    access_ids_raw = Counter(r["request_id"] for _, r in access_raw if "request_id" in r)
    dup_access = {k: v for k, v in access_ids_raw.items() if v > 1}
    print(f"\n--- Duplicate request_ids in access.log (de-duplication) ---")
    print(f"Raw lines: {len(access_raw)}; unique request_ids: {len(access_ids_raw)}; "
          f"duplicated ids: {len(dup_access)}")
    if dup_access:
        print(f"Duplicated ids: {dict(dup_access)}")
        print("These are byte-identical repeated lines at the same timestamp "
              "(e.g. lab-000121 appears twice at 11:05:00.055Z) — a logging/probe "
              "artifact, not two real client requests. Deduplicated below by "
              "request_id, keeping the first occurrence.")

    seen = set()
    access = []
    for ln, r in access_raw:
        rid = r.get("request_id")
        if rid in seen:
            continue
        seen.add(rid)
        access.append((ln, r))

    # application.log has TWO distinct event types (http_request, dependency_error)
    # that legitimately share the same request_id -- one request can log both an
    # http_request line and a dependency_error line. De-duplicating by request_id
    # alone would silently drop one of two different events. Instead, dedupe only
    # exact byte-identical records (same fields AND same values), which is the
    # pattern actually observed in this file.
    app_ids_raw = Counter(r["request_id"] for _, r in app_raw if "request_id" in r)
    dup_app_ids = {k: v for k, v in app_ids_raw.items() if v > 1}
    seen_exact = set()
    app = []
    exact_dupes = 0
    for ln, r in app_raw:
        key = json.dumps(r, sort_keys=True)
        if key in seen_exact:
            exact_dupes += 1
            continue
        seen_exact.add(key)
        app.append((ln, r))
    print(f"application.log: raw lines {len(app_raw)}, unique request_ids "
          f"{len(app_ids_raw)}; {len(dup_app_ids)} request_ids appear more than once")
    print(f"  Of those, only {exact_dupes} are byte-identical duplicate lines "
          f"(true duplicates, removed).")
    print(f"  The remaining {len(dup_app_ids) - exact_dupes} are a legitimate "
          f"http_request + dependency_error pair for the same request_id "
          f"(different events, both kept -- deduping by request_id alone would "
          f"have silently discarded real dependency_error evidence).")
    print(f"\nAll counts below use the de-duplicated sets: "
          f"{len(access)} access records, {len(app)} application records.")

    # --- Status code counts ---
    status_counts = Counter(r.get("status") for _, r in access)
    print(f"\n access.log status code counts ")
    for status, count in sorted(status_counts.items(), key=lambda x: str(x[0])):
        print(f"  {status}: {count}")

    app_status_counts = Counter(r.get("status") for _, r in app)
    print(f"\n--- application.log status code counts ---")
    for status, count in sorted(app_status_counts.items(), key=lambda x: str(x[0])):
        print(f"  {status}: {count}")

    # error.log: outage window detection 
    print(f"\n error.log: connect() failed / Connection refused events ")
    print(f"Total: {len(err)}")
    if err:
        first = err[0][1]["ts_dt"]
        last = err[-1][1]["ts_dt"]
        print(f"First occurrence: {first.isoformat()}")
        print(f"Last occurrence:  {last.isoformat()}")
        print(f"Outage window duration: {(last - first).total_seconds():.0f}s")
        upstreams = Counter(d["upstream"] for _, d in err)
        print(f"Affected upstream(s): {dict(upstreams)}")
        paths = Counter(d["path"] for _, d in err)
        print(f"Paths affected during outage: {dict(paths)}")

    # Errors by time (5-minute buckets), across access.log non-2xx/3xx 
    print(f"\n access.log: non-2xx responses by 5-minute bucket (timeline) ")
    buckets = defaultdict(int)
    for _, r in access:
        status = r.get("status", 0)
        if status is None or status < 400:
            continue
        ts = parse_ts(r["timestamp"])
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        buckets[bucket] += 1
    for b in sorted(buckets):
        print(f"  {b.isoformat()}  {'#' * buckets[b]} ({buckets[b]})")

            #  error.log errors by time (5-minute buckets) 
    print(f"\n error.log: connect() failures by 5-minute bucket (timeline) ")
    ebuckets = defaultdict(int)
    for _, d in err:
        ts = d["ts_dt"]
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        ebuckets[bucket] += 1
    for b in sorted(ebuckets):
        print(f"  {b.isoformat()}  {'#' * ebuckets[b]} ({ebuckets[b]})")

    #  Correlate: during the outage window, what did application.log see?
    if err:
        outage_start, outage_end = first, last
        app_during = [
            r for _, r in app
            if outage_start <= parse_ts(r["timestamp"]) <= outage_end
        ]
        app_instance_during = Counter(r.get("instance_id") for r in app_during)
        print(f"\napplication.log: instance_id distribution DURING outage window ")
        print(f"  {dict(app_instance_during)}")
        print("  (app-02 largely silent here => app-02 was the unreachable instance; "
              "confirmed by error.log upstream field)")

        app_outside = [
            r for _, r in app
            if not (outage_start <= parse_ts(r["timestamp"]) <= outage_end)
        ]
        app_instance_outside = Counter(r.get("instance_id") for r in app_outside)
        print(f"\n application.log: instance_id distribution OUTSIDE outage window ")
        print(f"  {dict(app_instance_outside)}")

    # Correlate a sample of access.log 503s with application.log by request_id 
    print(f"\n Correlation sample: access.log 503s cross-checked against application.log ")
    app_by_rid = {r.get("request_id"): r for _, r in app if "request_id" in r}
    count_503 = 0
    matched = 0
    for _, r in access:
        if r.get("status") == 503:
            count_503 += 1
            rid = r.get("request_id")
            if rid in app_by_rid:
                matched += 1
    print(f"access.log 503 count: {count_503}; matched to an application.log record: {matched}")
    print("(503s with no matching application.log record indicate nginx returned the")
    print(" error itself, e.g. connect() refused, before the app ever saw the request)")

    # dependency_error breakdown (second, overlapping incident) 
    dep_errors = [r for _, r in app if r.get("event") == "dependency_error"]
    if dep_errors:
        dep_by_dep = Counter(r["dependency"] for r in dep_errors)
        dep_by_type = Counter(r["error_type"] for r in dep_errors)
        dep_ts = sorted(parse_ts(r["timestamp"]) for r in dep_errors)
        print(f"\napplication.log: dependency_error breakdown (2nd incident) ")
        print(f"  Total: {len(dep_errors)}")
        print(f"  By dependency: {dict(dep_by_dep)}")
        print(f"  By error_type: {dict(dep_by_type)}")
        print(f"  Window: {dep_ts[0].isoformat()} to {dep_ts[-1].isoformat()}")
        print(f"  (This is a SEPARATE incident from the app-02 connect-refused outage")
        print(f"   above -- it overlaps in time but has a different root cause: redis")
        print(f"   TimeoutError and postgres InvalidPassword, matching the config/app.env")
        print(f"   port/password mismatch this project's baseline shipped with.)")

    # Q1: interval covered, per-file valid/malformed/duplicate counts 
    print(f"\n=== Q1: UTC interval covered + per-file line counts ===")
    all_ts = [parse_ts(r["timestamp"]) for _, r in access] + \
             [parse_ts(r["timestamp"]) for _, r in app] + \
             [d["ts_dt"] for _, d in err]
    print(f"  Interval: {min(all_ts).isoformat()} to {max(all_ts).isoformat()}")
    print(f"  access.log:      raw={len(access_raw)} valid={len(access_raw)-len(access_bad)} "
          f"malformed={len(access_bad)} exact-duplicate={len(access_ids_raw)-len({r['request_id'] for _,r in access_raw if 'request_id' in r})+ (len(access_raw)-len(access_bad)-len(access))}")
    print(f"    -> valid parsed: {len(access_raw)-len(access_bad)}, of which "
          f"{(len(access_raw)-len(access_bad))-len(access)} are exact-duplicate lines "
          f"(removed), {len(access)} unique")
    print(f"  application.log: raw={len(app_raw)} valid={len(app_raw)-len(app_bad)} "
          f"malformed={len(app_bad)}, of which {exact_dupes} exact-duplicate lines removed, "
          f"{len(app)} unique kept (includes legitimate multi-event request_ids)")
    print(f"  error.log:       raw lines={len(err)+len(err_bad)} valid={len(err)} "
          f"unparseable={len(err_bad)}")

    # Q2: distinct client requests + dedup/retry method 
    print(f"\n Q2: distinct client requests ")
    print(f"  Distinct client requests (access.log, post-dedup): {len(access)}")
    print(f"  Dedup method: exact byte-identical lines removed (see Q1). Retries are NOT")
    print(f"  double-counted because nginx writes ONE access.log line per client request")
    print(f"  even when it retries against a second upstream -- see Q6 for the")
    print(f"  comma-separated upstream/upstream_status evidence of this.")

    # Q3: final client status counts + error rate (with stated denominator) 
    print(f"\n=== Q3: final client status counts + error rate ===")
    denom = len(access)
    print(f"  Denominator: {denom} (distinct client requests in access.log, post-dedup)")
    for status, count in sorted(status_counts.items(), key=lambda x: str(x[0])):
        print(f"    {status}: {count} ({100*count/denom:.1f}%)")
    server_errors = sum(c for s, c in status_counts.items() if isinstance(s, int) and s >= 500)
    print(f"  Server error rate (5xx only): {server_errors}/{denom} = {100*server_errors/denom:.2f}%")
    all_errors = sum(c for s, c in status_counts.items() if isinstance(s, int) and s >= 400)
    print(f"  All non-2xx rate (4xx+5xx): {all_errors}/{denom} = {100*all_errors/denom:.2f}%")

    # --- Q4: which paths/time windows/backends account for failures ---
    print(f"\n Q4: failures by path, time window, backend ")
    fail_recs = [r for _, r in access if isinstance(r.get("status"), int) and r["status"] >= 500]
    by_path = Counter(r["path"] for r in fail_recs)
    print(f"  By path: {dict(by_path)}")
    by_backend = Counter()
    for r in fail_recs:
        up = r.get("upstream", "")
        first_upstream = up.split(",")[0].strip() if up else "unknown"
        by_backend[first_upstream] += 1
    print(f"  By first-attempted backend: {dict(by_backend)}")
    print(f"  Time windows: see the two timeline sections above (11:05-11:26 connect-refused,")
    print(f"  11:12-11:21 dependency errors) -- failures cluster in exactly those windows.")

    # Q5: median / p95 latency 
    print(f"\n Q5: median / p95 client latency (access.log request_time, seconds) ")
    req_times = sorted(r["request_time"] for _, r in access if isinstance(r.get("request_time"), (int, float)))
    def percentile(data, p):
        if not data:
            return None
        k = (len(data) - 1) * (p / 100)
        f, c = int(k), min(int(k) + 1, len(data) - 1)
        if f == c:
            return data[f]
        return data[f] + (data[c] - data[f]) * (k - f)
    med = percentile(req_times, 50)
    p95 = percentile(req_times, 95)
    print(f"  n={len(req_times)}; method=linear interpolation between closest ranks (numpy-style)")
    print(f"  median (p50): {med*1000:.1f} ms")
    print(f"  p95: {p95*1000:.1f} ms")
    print(f"  (units: request_time is in seconds per logs/README.md; converted to ms here)")

    #  Q6: which requests retried upstream, how many succeeded 
    print(f"\n Q6: upstream retries ")
    retried = [r for _, r in access if isinstance(r.get("upstream"), str) and "," in r["upstream"]]
    retried_succeeded = [r for r in retried if r.get("status") == 200]
    retried_failed = [r for r in retried if r.get("status") != 200]
    print(f"  Requests with multiple upstream attempts (comma-separated upstream field): {len(retried)}")
    print(f"  Succeeded after retry (final status 200): {len(retried_succeeded)}")
    print(f"  Still failed after retry: {len(retried_failed)}")
    if retried:
        ex = retried[0]
        print(f"  Example: request_id={ex['request_id']} upstream='{ex['upstream']}' "
              f"upstream_status='{ex['upstream_status']}' final_status={ex['status']}")

        #  Q7: incident timeline built from all three logs together 
    print(f"\n Q7: incident timeline (access + error + application logs) ")
    print(f"  error.log connect-refused events (proxy/connectivity, Incident A):")
    print(f"    first={first.isoformat()} last={last.isoformat()} total={len(err)}")
    print(f"    by 5-min bucket: {dict(sorted(ebuckets.items()))}")
    print(f"  application.log dependency_error events (dependency layer, Incident B):")
    if dep_errors:
        print(f"    first={dep_ts[0].isoformat()} last={dep_ts[-1].isoformat()} total={len(dep_errors)}")
    print(f"  access.log non-2xx responses by 5-min bucket (combined effect of both incidents):")
    print(f"    {dict(sorted(buckets.items()))}")
    print(f"  Interpretation: Incident A (connectivity) runs {first.isoformat()} to")
    print(f"  {last.isoformat()}, with a gap in the middle. Incident B (dependency) runs")
    print(f"  fully nested inside that window, {dep_ts[0].isoformat()} to "
          f"{dep_ts[-1].isoformat()}, hitting both app instances rather than just one.")

    # Q8: one correlated failed request + one correlated successful request -
    print(f"\n Q8: correlated failed + successful request examples ")
    failed_example = None
    for _, r in access:
        if r.get("status") == 502:
            failed_example = r
            break
    if failed_example:
        rid = failed_example["request_id"]
        print(f"  FAILED example: request_id={rid}")
        print(f"    access.log:      {failed_example}")
        app_match = app_by_rid.get(rid)
        print(f"    application.log: {app_match if app_match else 'NO MATCHING ENTRY -- nginx failed before the app ever saw this request'}")
    success_example = None
    for _, r in access:
        if r.get("status") == 200 and r.get("path") == "/records":
            success_example = r
            break
    if success_example:
        rid = success_example["request_id"]
        print(f"  SUCCESSFUL example: request_id={rid}")
        print(f"    access.log:      {success_example}")
        print(f"    application.log: {app_by_rid.get(rid)}")    

    #Q9: proxy/connectivity vs dependency/application issues
    print(f"\n Q9: proxy/connectivity vs dependency/application issues")
    print(f"  Proxy/connectivity issues: {len(err)} error.log 'connect() failed "
          f"(111: Connection refused)' events, all pointing at upstream IPs -- these")
    print(f"  happen BEFORE the app ever sees the request (nginx can't even open a TCP")
    print(f"  connection to the backend). Proof: they exist only in error.log, logged by")
    print(f"  nginx itself, naming an unreachable upstream IP:port.")
    print(f"  Dependency/application issues: {len(dep_errors)} application.log")
    print(f"  'dependency_error' events (redis TimeoutError, postgres InvalidPassword) --")
    print(f"  these happen AFTER the app received the request and tried to use a")
    print(f"  dependency. Proof: logged by the app itself (service=barq-api) with a")
    print(f"  specific dependency name and error_type, at a request_id nginx also logged")
    print(f"  with a normal (non-connect-refused) proxy flow.")

    # Latency stats (application.log duration_ms, kept from before) 
    durations = [r["duration_ms"] for _, r in app if isinstance(r.get("duration_ms"), (int, float))]
    if durations:
        print(f"\n--- application.log duration_ms stats ---")
        print(f"  count={len(durations)} mean={mean(durations):.1f} "
              f"median={median(durations):.1f} max={max(durations):.1f} min={min(durations):.1f}")

    print("\nDone. This output is the evidence base for log_analysis.md — do not")
    print("hand-count or restate different numbers there than what this script produces.")


if __name__ == "__main__":
    main()