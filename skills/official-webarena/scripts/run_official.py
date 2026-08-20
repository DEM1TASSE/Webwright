#!/usr/bin/env python3
"""Lane runner over the official-webarena skill pipeline. Resumable, bounded concurrency.

Each job shells out to skills/official-webarena/scripts/official_webarena.py pipeline, which
runs Webwright, waits for the three final artifacts, and scores the saved state with the
pinned official evaluator. This layer only schedules; it never touches scoring.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WW = HERE.parents[2]                      # repository root
PIPELINE = HERE / "official_webarena.py"
PY = Path(os.environ.get("WEBWRIGHT_PYTHON") or WW / ".venv" / "bin" / "python")

# Outcomes that are real benchmark observations; anything else is an attempt worth retrying.
RESUMABLE = {"scored_correct", "scored_incorrect"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def site_lanes(jobs, per_site_workers):
    grouped = {}
    for job in jobs:
        grouped.setdefault(job[0], []).append(job)
    lanes = []
    for site_jobs in grouped.values():
        buckets = [[] for _ in range(min(per_site_workers, len(site_jobs)))]
        for index, job in enumerate(site_jobs):
            buckets[index % len(buckets)].append(job)
        lanes.extend(buckets)
    return lanes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webarena-root", required=True)
    ap.add_argument("--deployment-config", required=True)
    ap.add_argument("--task-ids", required=True, help="JSON file holding a list of task ids")
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument("--workers", type=int, default=64)
    ap.add_argument("--per-site-workers", type=int, default=12)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--sites", default="")
    ap.add_argument("--limit-per-site", type=int, default=0)
    ap.add_argument("--task-id", type=int, action="append")
    ap.add_argument("--progress", default="")
    args = ap.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing")

    tasks = {t["task_id"]: t for t in load(Path(args.webarena_root) / "config_files/test.raw.json")}
    wanted = load(args.task_ids)
    jobs = [(tasks[i]["sites"][0], i) for i in wanted if i in tasks]
    if args.task_id:
        keep_ids = set(args.task_id)
        jobs = [j for j in jobs if j[1] in keep_ids]
    if args.sites:
        keep = {s.strip() for s in args.sites.split(",") if s.strip()}
        jobs = [j for j in jobs if j[0] in keep]
    if args.limit_per_site:
        seen = {}
        capped = []
        for job in jobs:
            seen[job[0]] = seen.get(job[0], 0) + 1
            if seen[job[0]] <= args.limit_per_site:
                capped.append(job)
        jobs = capped

    active, active_lock = set(), threading.Lock()
    stopping = threading.Event()

    def stop_active(*_):
        stopping.set()
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
        result = Path(args.results_root) / site / f"task{task_id}.json"
        if result.exists():
            try:
                if load(result).get("evaluation", {}).get("status") in RESUMABLE:
                    rec = load(result)
                    return {"site": site, "task_id": task_id, "status": "resumed",
                            "score": rec["evaluation"].get("score")}
            except (OSError, ValueError):
                pass
        if stopping.is_set():
            return {"site": site, "task_id": task_id, "status": "skipped_stopping"}
        out_dir = Path(args.output_root) / site
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [str(PY), str(PIPELINE), "pipeline", "--task-id", str(task_id),
               "--webarena-root", args.webarena_root,
               "--deployment-config", args.deployment_config,
               "--output-dir", str(out_dir),
               "--config", "base.yaml", "--config", args.model_config,
               "--model-config", args.model_config,
               "--timeout", str(args.timeout)]
        started = time.time()
        proc = subprocess.Popen(cmd, cwd=str(WW), text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=os.environ.copy(),
                                start_new_session=True)
        with active_lock:
            active.add(proc.pid)
        out, err = proc.communicate()
        with active_lock:
            active.discard(proc.pid)

        payload = {}
        try:
            payload = json.loads(out[out.index("{"):]) if "{" in out else {}
        except ValueError:
            payload = {}
        evaluation = payload.get("evaluation") or {}
        if payload:
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        return {"site": site, "task_id": task_id,
                "status": "ok" if proc.returncode == 0 else "process_error",
                "returncode": proc.returncode,
                "score": evaluation.get("score"),
                "eval_status": evaluation.get("status"),
                "eval_types": evaluation.get("eval_types"),
                "timed_out": (payload.get("run") or {}).get("timed_out"),
                "wall_seconds": round(time.time() - started, 1),
                "stderr": err.strip()[-400:]}

    print_lock = threading.Lock()
    progress_path = Path(args.progress) if args.progress else None
    done, total = [0], len(jobs)

    def run_lane(lane):
        rows = []
        for job in lane:
            row = run(job)
            with print_lock:
                done[0] += 1
                row["done"], row["total"] = done[0], total
                line = json.dumps(row, ensure_ascii=False)
                print(line, flush=True)
                if progress_path:
                    with progress_path.open("a", encoding="utf-8") as f:
                        f.write(line + "\n")
            rows.append(row)
        return rows

    lanes = site_lanes(jobs, args.per_site_workers)
    print(json.dumps({"event": "start", "tasks": total, "lanes": len(lanes),
                      "workers": args.workers}), flush=True)
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_lane, lane) for lane in lanes]
        for future in concurrent.futures.as_completed(futures):
            for row in future.result():
                failures += row["status"] == "process_error"
    print(json.dumps({"event": "end", "process_errors": failures}), flush=True)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
