#!/usr/bin/env python3
"""Run the frozen multi-site plan with bounded, resumable concurrency."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resumable_result(path):
    """Only resume records written by the current failure-aware harness."""
    path = Path(path)
    if not path.exists():
        return False
    try:
        record = load(path)
    except (OSError, ValueError):
        return False
    return "process_returncode" in record


def library_for_site(root, site):
    """Resolve an independent site library, falling back to a legacy shared root."""
    root = Path(root)
    candidate = root / site
    return candidate if candidate.is_dir() else root


def planned_jobs(manifest_path, phase):
    manifest_path = Path(manifest_path)
    manifest = load(manifest_path)
    jobs = []
    for site, relative in manifest["sites"].items():
        split_path = manifest_path.parent / relative
        split = load(split_path)
        if phase == "train":
            task_ids = split["source"]["task_ids"]
            modes = ["scratch"]
        else:
            task_ids = [tid for group in split["heldout"] for tid in group["task_ids"]]
            modes = ["scratch", "routed"]
        for task_id in task_ids:
            for mode in modes:
                jobs.append((site, split_path, task_id, mode))
    return jobs


def partition_site_jobs(jobs, per_site_workers):
    """Create sequential lanes while bounding concurrency within each site."""
    if per_site_workers < 1:
        raise ValueError("per_site_workers must be positive")
    by_site = {}
    for job in jobs:
        by_site.setdefault(job[0], []).append(job)
    lanes = []
    for site_jobs in by_site.values():
        site_lanes = [[] for _ in range(min(per_site_workers, len(site_jobs)))]
        for index, job in enumerate(site_jobs):
            site_lanes[index % len(site_lanes)].append(job)
        lanes.extend(site_lanes)
    return lanes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["train", "test"])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--results-root", required=True)
    parser.add_argument("--model-config", required=True)
    parser.add_argument("--eval-python", required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--per-site-workers", type=int, default=1)
    parser.add_argument("--sites", nargs="+")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is missing; load the model credential before launching runs"
        )
    jobs = planned_jobs(args.manifest, args.phase)
    if args.sites:
        unknown = set(args.sites) - {job[0] for job in jobs}
        if unknown:
            raise SystemExit(f"unknown sites: {sorted(unknown)}")
        jobs = [job for job in jobs if job[0] in set(args.sites)]

    def execute(job):
        site, split_path, task_id, mode = job
        results = Path(args.results_root) / site
        runs = Path(args.runs_root) / site
        result = results / f"task{task_id}_{mode}.json"
        is_resumable = resumable_result(result)
        if is_resumable and not args.force:
            return {"site": site, "task_id": task_id, "mode": mode, "status": "resumed"}
        command = [
            sys.executable, str(HERE / "cross_task_eval.py"), "run", str(task_id), mode,
            "--split", str(split_path),
            "--dataset", args.dataset,
            "--config", args.config,
            "--routed-library", str(library_for_site(args.library, site)),
            "--model-config", args.model_config,
            "--eval-python", args.eval_python,
            "--runs", str(runs),
            "--results", str(results),
            "--timeout", str(args.timeout),
        ]
        if args.phase == "train":
            command.append("--allow-any-task")
        if args.force or (result.exists() and not is_resumable):
            command.append("--force")
        proc = subprocess.run(command, text=True, capture_output=True, env=os.environ.copy())
        return {
            "site": site, "task_id": task_id, "mode": mode,
            "status": "ok" if proc.returncode == 0 else "process_error",
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip()[-2000:],
            "stderr": proc.stderr.strip()[-2000:],
        }

    failures = 0
    def execute_site(site_jobs):
        rows = []
        for job in site_jobs:
            row = execute(job)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            rows.append(row)
        return rows

    lanes = partition_site_jobs(jobs, args.per_site_workers)
    # A worker owns a sequential site lane. Multiple lanes per site are opt-in and appropriate
    # only for tasks whose expected behavior is non-mutating.
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute_site, lane) for lane in lanes]
        for future in concurrent.futures.as_completed(futures):
            for row in future.result():
                failures += int(row["status"] == "process_error")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
