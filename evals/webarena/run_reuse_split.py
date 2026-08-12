#!/usr/bin/env python3
"""Run the fixed reuse split with resumable, bounded concurrency."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resumable_result(record):
    """Infrastructure failures are attempts, not completed benchmark observations."""
    return record.get("run_status") in {
        "scored_correct", "scored_incorrect", "agent_timeout_or_incomplete",
    }


def build_jobs(split):
    return [
        (site, task_id)
        for site, rows in split["train"].items()
        for row in rows
        for task_id in row["build_task_ids"]
    ]


def site_lanes(jobs, per_site_workers=1):
    """Create sequential lanes with bounded concurrency inside each site."""
    if per_site_workers < 1:
        raise ValueError("per_site_workers must be positive")
    grouped = {}
    for job in jobs:
        grouped.setdefault(job[0], []).append(job)
    lanes = []
    for site_jobs in grouped.values():
        site = [[] for _ in range(min(per_site_workers, len(site_jobs)))]
        for index, job in enumerate(site_jobs):
            site[index % len(site)].append(job)
        lanes.extend(site)
    return lanes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--runs-root", required=True)
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument("--eval-python", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--per-site-workers", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--task-id", type=int, action="append")
    args = ap.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing")

    split = load(args.split)
    jobs = build_jobs(split)
    if args.task_id:
        selected = set(args.task_id)
        jobs = [job for job in jobs if job[1] in selected]
        missing = selected - {task_id for _, task_id in jobs}
        if missing:
            raise SystemExit(f"tasks outside TRAIN build set: {sorted(missing)}")

    # cross_task_eval only needs a heldout-shaped object during argument loading;
    # --allow-any-task authorizes these TRAIN tasks. Keep it local to this run root.
    compat_split = Path(args.runs_root) / "train_compat_split.json"
    compat_split.parent.mkdir(parents=True, exist_ok=True)
    compat_split.write_text(json.dumps({"heldout": []}) + "\n", encoding="utf-8")

    active = set()
    active_lock = threading.Lock()

    def stop_active(*_):
        with active_lock:
            pids = list(active)
        for pid in pids:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGINT, stop_active)
    signal.signal(signal.SIGTERM, stop_active)

    def run(job):
        site, task_id = job
        results = Path(args.results_root) / site
        runs = Path(args.runs_root) / site
        result = results / f"task{task_id}_scratch.json"
        if result.exists():
            try:
                record = load(result)
                if resumable_result(record):
                    return {"site": site, "task_id": task_id, "status": "resumed",
                            "correct": record.get("correct"), "steps": record.get("steps")}
            except (OSError, ValueError):
                pass
        cmd = [
            sys.executable, str(HERE / "cross_task_eval.py"), "run", str(task_id), "scratch",
            "--split", str(compat_split), "--dataset", args.dataset, "--config", args.config,
            "--runs", str(runs), "--results", str(results),
            "--model-config", args.model_config, "--eval-python", args.eval_python,
            "--timeout", str(args.timeout), "--allow-any-task",
        ]
        if result.exists():
            cmd.append("--force")
        proc = subprocess.Popen(
            cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=os.environ.copy(), start_new_session=True,
        )
        with active_lock:
            active.add(proc.pid)
        stdout, stderr = proc.communicate()
        with active_lock:
            active.discard(proc.pid)
        record = load(result) if result.exists() else {}
        return {"site": site, "task_id": task_id,
                "status": "ok" if proc.returncode == 0 else "process_error",
                "returncode": proc.returncode, "correct": record.get("correct"),
                "steps": record.get("steps"), "timed_out": record.get("timed_out"),
                "stderr": stderr.strip()[-500:]}

    print_lock = threading.Lock()

    def run_lane(lane):
        rows = []
        for job in lane:
            row = run(job)
            with print_lock:
                print(json.dumps(row, ensure_ascii=False), flush=True)
            rows.append(row)
        return rows

    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_lane, lane)
                   for lane in site_lanes(jobs, args.per_site_workers)]
        for future in concurrent.futures.as_completed(futures):
            for row in future.result():
                failures += row["status"] == "process_error"
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
