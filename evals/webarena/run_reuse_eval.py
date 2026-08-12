#!/usr/bin/env python3
"""Run isolated T1/T2 arms for the frozen reuse split."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_reuse_split import resumable_result, site_lanes  # noqa: E402


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_jobs(split, partition):
    jobs = []
    if partition == "t1":
        for site, rows in split["train"].items():
            for row in rows:
                for task_id in row.get("t1_heldout_task_ids", []):
                    jobs.append((site, row["intent_template_id"], task_id))
    else:
        for site, rows in split["test"].items():
            for row in rows:
                for task_id in row.get("t2_task_ids", []):
                    jobs.append((site, row["intent_template_id"], task_id))
    return jobs


def workflow_map(events_path):
    if not Path(events_path).exists():
        return {}
    return {
        (row["site"], row["template_id"]): row["skill_ids"][0]
        for row in load(events_path)
        if row.get("status") == "built" and row.get("skill_ids")
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--partition", required=True, choices=["t1", "t2"])
    ap.add_argument("--arm", required=True, choices=["scratch", "workflow", "primitive"])
    ap.add_argument("--split", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--runs-root", required=True)
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--workflow-library", required=True)
    ap.add_argument("--workflow-events", required=True)
    ap.add_argument("--primitive-library", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument("--eval-python", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--per-site-workers", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()
    if args.partition == "t1" and args.arm == "primitive":
        raise SystemExit("T1 has no primitive arm in the frozen protocol")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing")

    jobs = build_jobs(load(args.split), args.partition)
    skills = workflow_map(args.workflow_events)
    compat = Path(args.runs_root) / args.partition / args.arm / "eval_split.json"
    compat.parent.mkdir(parents=True, exist_ok=True)
    compat.write_text(json.dumps({
        "heldout": [{"intent_template_id": template, "task_ids": [task_id]}
                    for _, template, task_id in jobs]
    }) + "\n")

    def run(job):
        site, template_id, task_id = job
        runs = Path(args.runs_root) / args.partition / args.arm / site
        results = Path(args.results_root) / args.partition / args.arm / site
        result = results / f"task{task_id}_{args.arm}.json"
        if result.exists():
            try:
                record = load(result)
                if resumable_result(record):
                    return {"site": site, "task_id": task_id, "status": "resumed",
                            "correct": record.get("correct"), "steps": record.get("steps")}
            except (OSError, ValueError):
                pass
        cmd = [
            sys.executable, str(HERE / "cross_task_eval.py"), "run", str(task_id), args.arm,
            "--split", str(compat), "--dataset", args.dataset, "--config", args.config,
            "--runs", str(runs), "--results", str(results),
            "--workflow-library", args.workflow_library,
            "--candidate-library", args.primitive_library,
            "--model-config", args.model_config, "--eval-python", args.eval_python,
            "--timeout", str(args.timeout), "--strict-arm-isolation",
        ]
        if args.partition == "t1" and args.arm == "workflow":
            cmd += ["--workflow-skill-id",
                    skills.get((site, template_id), f"__missing_template_{template_id}")]
        if result.exists():
            cmd.append("--force")
        proc = subprocess.run(cmd, text=True, capture_output=True)
        record = load(result) if result.exists() else {}
        return {"site": site, "task_id": task_id,
                "status": "ok" if proc.returncode == 0 else "process_error",
                "returncode": proc.returncode, "correct": record.get("correct"),
                "steps": record.get("steps"), "run_status": record.get("run_status"),
                "stderr": proc.stderr[-500:]}

    def lane(items):
        rows = []
        for item in items:
            row = run(item)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            rows.append(row)
        return rows

    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(lane, items)
                   for items in site_lanes(jobs, args.per_site_workers)]
        for future in concurrent.futures.as_completed(futures):
            failures += sum(row["status"] == "process_error" for row in future.result())
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
