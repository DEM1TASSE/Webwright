#!/usr/bin/env python3
"""Explain a NetworkEventEvaluator score, so a 0 can be attributed.

Separates the cases that matter:

  NOT_RECORDED   nothing in the HAR touches that path at all -> suspect the recorder
  WRONG_SHAPE    the path was requested, but the URL/method the evaluator anchors
                 on never appeared (e.g. the agent POSTed straight to the endpoint
                 and skipped the suffix the site's own form produces)
  FIELD_MISMATCH the request matched and was compared; some field differs
  PASS           scored 1.0

Usage: diagnose_har.py <task_id> <run_dir> [har_name]
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EVAL_PY = os.environ.get("WA_EVAL_PYTHON", "")
CONFIG = os.environ.get("WA_CONFIG", "")

DETAIL = r"""
import json, sys
from pathlib import Path
from webarena_verified.api import WebArenaVerified
tid, resp, har, cfg = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
r = WebArenaVerified(config=cfg).evaluate_task(task_id=tid, agent_response=resp, network_trace=har)
out = []
for e in r.evaluators_results:
    out.append({
        "name": e.evaluator_name, "score": e.score,
        "expected": str(getattr(e, "expected", ""))[:1200],
        "actual": str(getattr(e, "actual", ""))[:1200],
        "error": str(getattr(e, "error_msg", "") or "")[:400],
        "assertions": str(getattr(e, "assertions", "") or "")[:800],
    })
print(json.dumps(out))
"""


def expected_specs(task_id):
    ds = os.environ.get("WA_DATASET", "")
    if not ds:
        return []
    task = next(t for t in json.loads(Path(ds).read_text()) if t["task_id"] == task_id)
    out = []
    for e in task.get("eval", []):
        if e.get("evaluator") == "NetworkEventEvaluator":
            out.append(e.get("expected", {}))
    return out


def path_of(url):
    return "/" + str(url).split("//", 1)[-1].split("/", 1)[-1].split("?")[0]


def _all_records(rec_dir):
    out = []
    for f in Path(rec_dir).glob("http_*.jsonl"):
        for line in f.read_text(errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def near_misses(rec_dir, expected_url):
    """Recorded requests near the expected URL, relaxing the prefix until something hits.

    Returns (level, hits) where level says how much had to be dropped:
      "exact path"    the full expected path was requested
      "same endpoint" same path family, different id/target (agent hit the wrong thing)
      "same area"     only a shallow prefix matched
      None            nothing anywhere near it
    """
    stem = re.sub(r"^\^?__[A-Z_]+__", "", str(expected_url))
    stem = re.split(r"[\\(\[\$]", stem)[0].rstrip("/")
    parts = [p for p in stem.split("/") if p and not p.startswith("\\")]
    if not parts:
        return None, []
    records = _all_records(rec_dir)
    labels = ["exact path", "same endpoint", "same area"]
    for drop, label in enumerate(labels):
        keep = parts[: len(parts) - drop] if drop else parts
        if not keep:
            break
        needle = "/" + "/".join(keep)
        hits = [(r.get("method"), r.get("status"), r.get("url"), (r.get("post_data") or "")[:90])
                for r in records if needle in r.get("url", "")]
        if hits:
            return label, hits
    return None, []


def main(task_id, run_dir, har_name="final.trimmed.har"):
    task_id = int(task_id)
    run_dir = Path(run_dir)
    har = run_dir / har_name
    resp = run_dir / "agent_response.json"
    if not har.exists():
        sys.exit(f"missing {har}")

    p = subprocess.run([EVAL_PY, "-c", DETAIL, str(task_id), str(resp), str(har), CONFIG],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(p.stderr.strip()[-400:])
    results = json.loads(p.stdout.strip().splitlines()[-1])

    net = next((r for r in results if r["name"] == "NetworkEventEvaluator"), None)
    if net is None:
        print("no NetworkEventEvaluator for this task")
        return

    # this run's recording only -- a sibling task's _rec would give bogus hits
    key = re.sub(r"_\d{8}_\d{6}$", "", run_dir.name)
    rec_dir = run_dir.parent / "_rec" / key
    rec_dirs = [rec_dir] if rec_dir.is_dir() else []

    print(f"task {task_id}  har={har_name}  score={net['score']}")
    if net["score"] == 1.0:
        print("  PASS")
        return

    specs = expected_specs(task_id)
    levels = [near_misses(d, s.get("url", ""))[0] for d in rec_dirs for s in specs]
    best = next((l for l in ("exact path", "same endpoint", "same area") if l in levels), None)
    if net["actual"] in ("[]", "None", ""):
        verdict, note = {
            "exact path": ("WRONG_SHAPE",
                           "the exact path was requested, but never in the url/method shape "
                           "the evaluator anchors on"),
            "same endpoint": ("WRONG_TARGET",
                              "the same endpoint was used against a different id/target"),
            "same area": ("WRONG_ROUTE",
                          "only a shallow prefix matched -- the agent took a different route "
                          "to the same goal (e.g. web form instead of REST API)"),
            None: ("NOT_RECORDED",
                   "nothing in the recording is anywhere near that path -- suspect the recorder"),
        }[best]
        print(f"  {verdict}: {note}")
    else:
        print("  FIELD_MISMATCH: an event matched url+method but a field differs")
        print(f"    actual   {net['actual'][:400]}")
    print(f"    expected {net['expected'][:400]}")
    if net["error"]:
        print(f"    error    {net['error']}")

    for spec in specs:
        url = spec.get("url", "")
        for d in rec_dirs:
            level, hits = near_misses(d, url)
            if not hits:
                continue
            print(f"  recorded ({level}) near {path_of(url)[:56]} :")
            for m, st, u, body in hits[:8]:
                print(f"    {m:6s} {st} {u.split('//')[-1].split('/',1)[-1][:70]}")
                if body:
                    print(f"           post={body}")
    if not rec_dirs:
        print("  (no _rec directory alongside the run - cannot check for near misses)")


if __name__ == "__main__":
    main(*sys.argv[1:])
