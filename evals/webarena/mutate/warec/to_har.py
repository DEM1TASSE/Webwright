#!/usr/bin/env python3
"""Turn recorded JSONL into HAR files the WebArena-Verified evaluator can read.

Emits two HARs per run:
  trajectory.har  -- everything the agent did (diagnostic)
  final.har       -- only the LAST final_runs/run_N window (the score)

Usage: python to_har.py <run_dir> [<rec_dir>]
       rec_dir defaults to <run_dir>/_rec
"""
import json
import os
import sys
from pathlib import Path


def entries_from(rec_dir):
    out = []
    for f in sorted(Path(rec_dir).glob("http_*.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    out.sort(key=lambda r: r.get("ts", 0))
    return out


def final_run_windows(run_dir):
    """[(name, t_start, t_end)] for each final_runs/run_N, ordered in time."""
    base = Path(run_dir) / "final_runs"
    wins = []
    if not base.exists():
        return wins
    for d in base.iterdir():
        if not d.is_dir():
            continue
        ts = [p.stat().st_mtime for p in d.rglob("*") if p.is_file()]
        ts.append(d.stat().st_mtime)
        wins.append([d.name, min(ts), max(ts)])
    wins.sort(key=lambda w: w[1])
    for i in range(len(wins) - 1):          # window ends where the next begins
        wins[i][2] = min(wins[i][2], wins[i + 1][1])
    if wins:
        wins[-1][2] = float("inf")
    return [tuple(w) for w in wins]


def har_entry(r):
    headers = lambda d: [{"name": k, "value": str(v)} for k, v in (d or {}).items()]
    post = r.get("post_data")
    req = {
        "method": r.get("method", "GET"), "url": r.get("url", ""),
        "httpVersion": "HTTP/1.1", "headers": headers(r.get("req_headers")),
        "queryString": [], "cookies": [], "headersSize": -1,
        "bodySize": len(post or ""),
    }
    if post:
        req["postData"] = {"mimeType": (r.get("req_headers") or {}).get(
            "Content-Type", "application/x-www-form-urlencoded"), "text": post}
    return {
        "startedDateTime": "1970-01-01T00:00:00.000Z",
        "time": 0, "request": req,
        "response": {
            "status": r.get("status") or 0, "statusText": "",
            "httpVersion": "HTTP/1.1", "headers": headers(r.get("resp_headers")),
            "cookies": [], "content": {"size": 0, "mimeType": "text/html"},
            "redirectURL": "", "headersSize": -1, "bodySize": -1,
        },
        "cache": {}, "timings": {"send": 0, "wait": 0, "receive": 0},
    }


def write_har(path, records):
    path.write_text(json.dumps({"log": {
        "version": "1.2", "creator": {"name": "warec", "version": "1"},
        "entries": [har_entry(r) for r in records],
    }}, ensure_ascii=False), encoding="utf-8")


EVAL_PY = os.environ.get("WA_EVAL_PYTHON", "")   # python with webarena_verified installed

TRIM = """
import json, sys
from pathlib import Path
from webarena_verified.core.utils.trim_network_logs import trim_har_file
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
print(json.dumps(trim_har_file(src, dst)))
"""


def trim(path):
    """Shrink to evaluation-relevant events using the evaluator's own logic."""
    import subprocess
    out = path.with_name(path.stem + ".trimmed.har")
    p = subprocess.run([EVAL_PY, "-c", TRIM, str(path), str(out)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return f"trim skipped ({p.stderr.strip().splitlines()[-1:] or ['?']})"
    st = json.loads(p.stdout.strip().splitlines()[-1])
    return (f"{st['original_entries']} -> {st['trimmed_entries']} entries "
            f"(-{st['reduction_percent']:.0f}% size) -> {out.name}")


def main(run_dir, rec_dir=None):
    run_dir = Path(run_dir)
    rec_dir = Path(rec_dir) if rec_dir else run_dir / "_rec"
    recs = entries_from(rec_dir)
    wins = final_run_windows(run_dir)

    write_har(run_dir / "trajectory.har", recs)
    if wins:
        name, t0, t1 = wins[-1]
        final = [r for r in recs if t0 <= r.get("ts", 0) <= t1]
    else:
        name, final = "<none>", []
    write_har(run_dir / "final.har", final)

    writes = [r for r in recs if r.get("method") in ("POST", "PUT", "PATCH", "DELETE")]
    print(f"records={len(recs)}  writes={len(writes)}  final_runs={len(wins)}  scoring_window={name}")
    print(f"  trajectory.har  {trim(run_dir / 'trajectory.har')}")
    print(f"  final.har       {trim(run_dir / 'final.har')}")
    for r in writes:
        print(f"    {r['ts']:.0f} {r.get('method'):6s} {str(r.get('status')):4s} {r.get('url','')[:88]}")


if __name__ == "__main__":
    main(*sys.argv[1:])
