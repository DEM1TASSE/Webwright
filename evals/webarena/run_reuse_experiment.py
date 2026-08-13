#!/usr/bin/env python3
"""Run all frozen reuse evaluation arms sequentially and resumably."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


STAGES = (("t1", "scratch"), ("t1", "workflow"),
          ("t2", "scratch"), ("t2", "workflow"), ("t2", "primitive"))
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    for name in ("split", "dataset", "config", "runs-root", "results-root",
                 "workflow-library", "workflow-events", "primitive-library",
                 "model-config", "eval-python"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--per-site-workers", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--start-at", choices=[f"{p}/{a}" for p, a in STAGES])
    args = parser.parse_args()
    started = args.start_at is None
    log = Path(args.results_root) / "orchestration.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    for partition, arm in STAGES:
        key = f"{partition}/{arm}"
        if not started:
            started = key == args.start_at
            if not started:
                continue
        command = [
            sys.executable, str(HERE / "run_reuse_eval.py"),
            "--partition", partition, "--arm", arm,
            "--split", args.split, "--dataset", args.dataset, "--config", args.config,
            "--runs-root", args.runs_root, "--results-root", args.results_root,
            "--workflow-library", args.workflow_library,
            "--workflow-events", args.workflow_events,
            "--primitive-library", args.primitive_library,
            "--model-config", args.model_config, "--eval-python", args.eval_python,
            "--workers", str(args.workers), "--per-site-workers", str(args.per_site_workers),
            "--timeout", str(args.timeout),
        ]
        print(json.dumps({"event": "stage_start", "stage": key}), flush=True)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "stage_start", "stage": key}) + "\n")
        returncode = subprocess.run(command).returncode
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "stage_end", "stage": key,
                                     "returncode": returncode}) + "\n")
        if returncode:
            return returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
