#!/usr/bin/env python3
"""Replay frozen reuse-arm scripts once on a reset Official WebArena deployment."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from cross_task_eval import agent_subprocess_env, score_navigate
from run_reuse_eval import serial_scope_lanes


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--partition", required=True, choices=["t1", "t2"])
    ap.add_argument("--arm", required=True, choices=["workflow", "primitive"])
    ap.add_argument("--task-ids-file", required=True)
    ap.add_argument("--serial-groups", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--replay-results-root", required=True)
    ap.add_argument("--webarena-tasks", required=True)
    ap.add_argument("--webarena-root", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    tasks = {int(row["task_id"]): row for row in load(args.dataset)}
    wanted = [int(value) for value in load(args.task_ids_file)]
    jobs = []
    for task_id in wanted:
        if task_id not in tasks:
            raise SystemExit(f"task {task_id} missing from dataset")
        jobs.append((tasks[task_id]["sites"][0], "mutate", 0, task_id))
    try:
        lanes = serial_scope_lanes(jobs, args.serial_groups)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    source_root = Path(args.results_root) / args.partition / args.arm
    output_root = Path(args.replay_results_root) / args.partition / args.arm

    def replay(job):
        site, _, _, task_id = job
        started = time.time()
        source = source_root / site / f"task{task_id}_{args.arm}.json"
        output = output_root / site / f"task{task_id}_{args.arm}.json"
        if not source.is_file():
            return {"site": site, "task_id": task_id, "status": "no_generation_result"}
        record = load(source)
        run_dir = Path(record.get("run_dir") or "")
        script = run_dir / "final_script.py"
        if not script.is_file():
            return {"site": site, "task_id": task_id, "status": "no_script"}
        workspace = run_dir / "replay"
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)
        for item in run_dir.rglob("*"):
            if item.is_dir() and "replay" not in item.relative_to(run_dir).parts:
                (workspace / item.relative_to(run_dir)).mkdir(parents=True, exist_ok=True)
        shutil.copy2(script, workspace / "final_script.py")
        try:
            proc = subprocess.run(
                [os.sys.executable, "final_script.py"], cwd=workspace,
                env={**agent_subprocess_env(), "WORKSPACE_DIR": str(workspace)},
                text=True, capture_output=True, timeout=args.timeout,
            )
            status = "completed" if proc.returncode == 0 else "process_error"
            returncode, stderr = proc.returncode, (proc.stderr or "")[-1000:]
        except subprocess.TimeoutExpired:
            status, returncode, stderr = "timeout", None, ""
        score, provenance = (None, {})
        if (workspace / "final_state.json").is_file():
            score, provenance = score_navigate(
                task_id, workspace, args.config, args.webarena_tasks,
                args.webarena_root, args.model_config,
            )
        payload = {
            "task_id": task_id, "site": site, "partition": args.partition, "arm": args.arm,
            "source_result": str(source), "source_run_dir": str(run_dir),
            "inline_score": record.get("score"), "inline_correct": record.get("correct"),
            "replay": {"status": status, "returncode": returncode, "stderr_tail": stderr,
                       "produced_state": (workspace / "final_state.json").is_file(),
                       "score": score, "correct": score == 1.0 if score is not None else None,
                       "evaluator": provenance,
                       "seconds": round(time.time() - started, 1)},
            "matches_inline": score == record.get("score") if score is not None else None,
            "deployment_config": str(Path(args.config).resolve()),
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"site": site, "task_id": task_id, "status": status,
                "inline_score": record.get("score"), "replay_score": score,
                "matches_inline": payload["matches_inline"]}

    def lane(items):
        rows = []
        for item in items:
            row = replay(item)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            rows.append(row)
        return rows

    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(lane, items) for items in lanes]
        for future in concurrent.futures.as_completed(futures):
            failures += sum(row["status"] not in {"completed"} for row in future.result())
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
