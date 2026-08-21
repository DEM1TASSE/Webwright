#!/usr/bin/env python3
"""Run isolated T1/T2 arms for the frozen reuse split."""
from __future__ import annotations

import argparse
import copy
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_reuse_split import resumable_result, site_lanes  # noqa: E402


SITE_PLACEHOLDERS = {
    "gitlab": "__GITLAB__",
    "shopping": "__SHOPPING__",
    "shopping_admin": "__SHOPPING_ADMIN__",
    "reddit": "__REDDIT__",
    "map": "__MAP__",
    "wikipedia": "__WIKIPEDIA__",
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_jobs(split, partition, sites=None):
    selected = set(sites or [])
    jobs = []
    if partition == "t1":
        for site, rows in split["train"].items():
            if selected and site not in selected:
                continue
            for row in rows:
                for task_id in row.get("t1_heldout_task_ids", []):
                    jobs.append((site, row.get("task_type", split.get("task_type", "retrieve")),
                                 row["intent_template_id"], task_id))
    else:
        for site, rows in split["test"].items():
            if selected and site not in selected:
                continue
            for row in rows:
                for task_id in row.get("t2_task_ids", []):
                    jobs.append((site, row.get("task_type", split.get("task_type", "retrieve")),
                                 row["intent_template_id"], task_id))
    return jobs


def select_task_subset(jobs, task_ids=None, exclude_task_ids=None):
    """Filter only within an already-frozen partition and reject silent membership mistakes."""
    jobs = list(jobs)
    if task_ids is not None:
        selected = set(task_ids)
        missing = selected - {job[3] for job in jobs}
        if missing:
            raise ValueError(f"tasks outside selected frozen partition/sites: {sorted(missing)}")
        jobs = [job for job in jobs if job[3] in selected]
    excluded = set(exclude_task_ids or [])
    return [job for job in jobs if job[3] not in excluded]


def workflow_map(events_path):
    if not Path(events_path).exists():
        return {}
    return {
        (row["site"], row["template_id"]): row["skill_ids"][0]
        for row in load(events_path)
        if row.get("status") == "built" and len(row.get("skill_ids") or []) == 1
    }


def write_site_compat_splits(runs_root, partition, arm, jobs):
    """Write immutable-per-site membership files for concurrent subset runners."""
    result = {}
    for site in sorted({job[0] for job in jobs}):
        compat = Path(runs_root) / partition / arm / site / "eval_split.json"
        compat.parent.mkdir(parents=True, exist_ok=True)
        compat.write_text(json.dumps({
            "heldout": [
                {"intent_template_id": template, "task_ids": [task_id]}
                for job_site, _, template, task_id in jobs if job_site == site
            ]
        }) + "\n")
        result[site] = compat
    return result


def write_task_compat_splits(runs_root, partition, arm, jobs):
    """Write one membership/type manifest per job for mixed Retrieve+Navigate runs."""
    result = {}
    for site, task_type, template, task_id in jobs:
        compat = (Path(runs_root) / partition / arm / "_task_splits" / site
                  / f"task{task_id}.json")
        compat.parent.mkdir(parents=True, exist_ok=True)
        compat.write_text(json.dumps({
            "task_type": task_type,
            "heldout": [{"intent_template_id": template, "task_ids": [task_id]}],
        }) + "\n", encoding="utf-8")
        result[(site, task_id)] = compat
    return result


def select_deployment(config, site, task_id):
    """Choose one replica deterministically while preserving the deployment config schema."""
    placeholder = SITE_PLACEHOLDERS[site]
    urls = list((config.get("environments", {}).get(placeholder, {}) or {}).get("urls") or [])
    if not urls:
        raise ValueError(f"deployment config has no URLs for {site} ({placeholder})")
    index = int(task_id) % len(urls)
    selected = copy.deepcopy(config)
    selected["environments"][placeholder]["urls"] = [urls[index]]
    selected["assignment"] = {
        "strategy": "task_id_modulo",
        "site": site,
        "task_id": int(task_id),
        "replica_index": index,
        "replica_count": len(urls),
        "url": urls[index],
    }
    return selected, urls[index]


def write_job_deployment_config(runs_root, partition, arm, config, site, task_id):
    selected, url = select_deployment(config, site, task_id)
    path = (Path(runs_root) / partition / arm / "_deployment_configs" / site
            / f"task{task_id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8")
    return path, url


def append_optional_eval_flags(cmd, *, scratch_first=False):
    """Append benchmark-independent routing controls to one task command."""
    if scratch_first:
        cmd.append("--scratch-first")
    return cmd


def serial_scope_lanes(jobs, serial_groups_path):
    """Return one ordered lane per official write scope.

    Every selected task must occur in exactly one scope.  Silently falling back to a
    site-wide or singleton lane would make a malformed scheduling manifest look safe.
    """
    groups = load(serial_groups_path)
    if not isinstance(groups, dict):
        raise ValueError("serial groups must be a JSON object mapping scope to task ids")
    placements = {}
    for scope, task_ids in groups.items():
        if not isinstance(task_ids, list):
            raise ValueError(f"serial group {scope!r} must contain a list of task ids")
        for raw_task_id in task_ids:
            task_id = int(raw_task_id)
            if task_id in placements:
                raise ValueError(
                    f"task {task_id} occurs in multiple serial groups: "
                    f"{placements[task_id]!r}, {scope!r}"
                )
            placements[task_id] = str(scope)
    missing = sorted(task_id for _, _, _, task_id in jobs if task_id not in placements)
    if missing:
        raise ValueError(f"selected serial tasks missing from serial groups: {missing[:20]}")
    lanes = {}
    for job in jobs:
        lanes.setdefault(placements[job[3]], []).append(job)
    return list(lanes.values())


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
    ap.add_argument("--webarena-tasks")
    ap.add_argument("--webarena-root")
    ap.add_argument("--vanilla-task-interface", action="store_true")
    ap.add_argument(
        "--scratch-first", action="store_true",
        help=("Freeze a task-only scratch plan before primitive metadata routing and allow "
              "primitives to replace only named plan steps."),
    )
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--per-site-workers", type=int, default=1)
    ap.add_argument(
        "--serial-groups",
        help=("Official serial_groups.json. Each write scope becomes a single-worker lane; "
              "--workers remains the global cap across lanes."),
    )
    ap.add_argument("--round-robin-deployments", action="store_true",
                    help="Distribute each site's tasks across every URL in its config.")
    ap.add_argument("--sites", nargs="*", help="Optional site subset; keeps the frozen split intact")
    ap.add_argument("--exclude-task-ids", nargs="*", type=int, default=[],
                    help="Recovery-only exclusions; the frozen split itself is unchanged")
    ap.add_argument(
        "--exclude-missing-workflows", action="store_true",
        help="T1 only: run the explicitly reported covered subset instead of failing preflight.",
    )
    ap.add_argument("--task-ids", nargs="*", type=int,
                    help="Development-only subset of the frozen partition")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()
    if args.partition == "t1" and args.arm == "primitive":
        raise SystemExit("T1 has no primitive arm in the frozen protocol")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing")

    partition_jobs = build_jobs(load(args.split), args.partition, args.sites)
    try:
        jobs = select_task_subset(partition_jobs, args.task_ids, args.exclude_task_ids)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    deployment_config = load(args.config)
    skills = workflow_map(args.workflow_events)
    if args.partition == "t1" and args.arm == "workflow":
        missing = [
            {"site": site, "template_id": template_id, "task_id": task_id}
            for site, _, template_id, task_id in jobs
            if (site, template_id) not in skills
        ]
        coverage = {
            "partition": "t1", "arm": "workflow", "jobs": len(jobs),
            "covered_jobs": len(jobs) - len(missing), "missing_jobs": len(missing),
            "missing": missing,
        }
        coverage_path = Path(args.runs_root) / "t1" / "workflow" / "coverage.json"
        coverage_path.parent.mkdir(parents=True, exist_ok=True)
        coverage_path.write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if missing:
            if not args.exclude_missing_workflows:
                raise SystemExit(
                    f"T1 workflow coverage incomplete: {len(missing)}/{len(jobs)} jobs; "
                    f"see {coverage_path}"
                )
            missing_ids = {row["task_id"] for row in missing}
            jobs = [job for job in jobs if job[3] not in missing_ids]
    # A process may run only a site subset while another subset is running concurrently.  A
    # shared compatibility split lets the later process overwrite the earlier process's task
    # membership.  Keep the small cross_task_eval compatibility manifest site-local instead.
    compat_by_site = write_site_compat_splits(
        args.runs_root, args.partition, args.arm, jobs,
    )
    compat_by_task = write_task_compat_splits(
        args.runs_root, args.partition, args.arm, jobs,
    )

    def run(job):
        site, task_type, template_id, task_id = job
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
        job_config = Path(args.config)
        deployment_url = ((deployment_config.get("environments", {}).get(
            SITE_PLACEHOLDERS[site], {}) or {}).get("urls") or [None])[0]
        if args.round_robin_deployments:
            job_config, deployment_url = write_job_deployment_config(
                args.runs_root, args.partition, args.arm,
                deployment_config, site, task_id,
            )
        cmd = [
            sys.executable, str(HERE / "cross_task_eval.py"), "run", str(task_id), args.arm,
            "--split", str(compat_by_task[(site, task_id)]), "--dataset", args.dataset,
            "--config", str(job_config),
            "--runs", str(runs), "--results", str(results),
            "--workflow-library", args.workflow_library,
            "--candidate-library", args.primitive_library,
            "--model-config", args.model_config, "--eval-python", args.eval_python,
            "--timeout", str(args.timeout), "--strict-arm-isolation",
        ]
        if args.webarena_tasks and args.webarena_root:
            cmd += ["--webarena-tasks", args.webarena_tasks,
                    "--webarena-root", args.webarena_root]
        append_optional_eval_flags(cmd, scratch_first=args.scratch_first)
        if task_type == "navigate":
            if not args.webarena_tasks or not args.webarena_root:
                return {"site": site, "task_id": task_id, "status": "process_error",
                        "returncode": 2, "correct": None, "steps": None,
                        "run_status": None,
                        "stderr": "Navigate requires --webarena-tasks and --webarena-root"}
            if args.vanilla_task_interface:
                cmd.append("--vanilla-task-interface")
        if args.partition == "t1" and args.arm == "workflow":
            cmd += ["--workflow-skill-id",
                    skills.get((site, template_id), f"__missing_template_{template_id}")]
        if result.exists():
            cmd.append("--force")
        proc = subprocess.run(cmd, text=True, capture_output=True)
        record = load(result) if result.exists() else {}
        if record:
            record["deployment_url"] = deployment_url
            record["deployment_config"] = str(job_config)
            result.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        return {"site": site, "task_id": task_id,
                "status": "ok" if proc.returncode == 0 else "process_error",
                "returncode": proc.returncode, "correct": record.get("correct"),
                "steps": record.get("steps"), "run_status": record.get("run_status"),
                "deployment_url": deployment_url,
                "stderr": proc.stderr[-500:]}

    def lane(items):
        rows = []
        for item in items:
            row = run(item)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            rows.append(row)
        return rows

    try:
        lanes = (serial_scope_lanes(jobs, args.serial_groups) if args.serial_groups
                 else site_lanes(jobs, args.per_site_workers))
    except ValueError as error:
        raise SystemExit(str(error)) from error

    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(lane, items) for items in lanes]
        for future in concurrent.futures.as_completed(futures):
            failures += sum(row["status"] == "process_error" for row in future.result())
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
