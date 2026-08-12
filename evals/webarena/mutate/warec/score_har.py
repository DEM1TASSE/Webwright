#!/usr/bin/env python3
"""Score a run's HARs with NetworkEventEvaluator, both windows side by side.

Usage: score_har.py <task_id> <run_dir> [config]
Runs under the eval venv via subprocess so this file itself has no deps.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

EVAL_PY = os.environ.get("WA_EVAL_PYTHON", "")   # python with webarena_verified installed
CONFIG = os.environ.get("WA_CONFIG", "")          # verified_config.json

SCORE = r"""
import json, sys
from pathlib import Path
from webarena_verified.api import WebArenaVerified
tid, resp, har, cfg = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
r = WebArenaVerified(config=cfg).evaluate_task(
        task_id=tid, agent_response=resp, network_trace=har)
print(json.dumps({e.evaluator_name: e.score for e in r.evaluators_results}))
"""


def score(task_id, resp, har, cfg=CONFIG):
    p = subprocess.run([EVAL_PY, "-c", SCORE, str(task_id), str(resp), str(har), str(cfg)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return {"error": (p.stderr.strip().splitlines() or ["?"])[-1][:160]}
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {"error": p.stdout[-160:]}


def main(task_id, run_dir, cfg=CONFIG):
    run_dir = Path(run_dir)
    resp = run_dir / "agent_response.json"
    if not resp.exists():                      # evaluator still needs a file
        resp = run_dir / "_stub_response.json"
        resp.write_text(json.dumps(
            {"task_type": "MUTATE", "status": "FAILURE", "retrieved_data": None}))

    for label in ("trajectory", "final"):
        for suffix in (".trimmed.har", ".har"):
            har = run_dir / f"{label}{suffix}"
            if har.exists():
                break
        else:
            print(f"{label:11s} <no har>")
            continue
        s = score(task_id, resp, har, cfg)
        net = s.get("NetworkEventEvaluator")
        ans = s.get("AgentResponseEvaluator")
        print(f"{label:11s} {har.name:26s} network={net} response={ans}"
              + (f"  {s['error']}" if "error" in s else ""))


if __name__ == "__main__":
    main(*sys.argv[1:])
