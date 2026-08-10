#!/usr/bin/env python3
"""Single-task Online-Mind2Web scratch/routed smoke pipeline."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tasks_by_id(path):
    raw = load_json(path)
    rows = raw if isinstance(raw, list) else raw.get("tasks", [])
    return {str(row["task_id"]): row for row in rows}


def task_text(task):
    return str(task.get("confirmed_task") or task.get("task_description") or task.get("task") or "")


def site_slug(website):
    host = (urlparse(website).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    slug = re.sub(r"[^a-z0-9]+", "_", host).strip("_")
    if not slug or not slug[0].isalpha():
        raise ValueError(f"cannot derive primitive site from {website!r}")
    return slug


def latest_workspace(root, task_id):
    candidates = []
    for child in Path(root).iterdir() if Path(root).is_dir() else []:
        metadata = child / "task.json"
        if not child.is_dir() or not metadata.is_file():
            continue
        try:
            identity = str(load_json(metadata).get("task_id") or "")
        except (OSError, ValueError):
            continue
        if identity == task_id:
            candidates.append(child)
    return max(candidates, default=None, key=lambda p: (p.stat().st_mtime_ns, p.name))


def solve_command(task, task_id, mode, runs, library, configs):
    text, website = task_text(task), task["website"]
    configs = list(configs)
    if configs and not any("base" in str(config) for config in configs):
        configs.insert(0, "base.yaml")
    if mode == "scratch":
        command = [sys.executable, "-m", "webwright.run.cli", "main", "-t", text,
                   "--task-id", task_id, "--start-url", website, "-o", str(runs)]
    else:
        command = [
            sys.executable, "-m", "webwright.skill_factory", "route",
            "--task", text, "--task-id", task_id, "--start-url", website,
            "--library", str(library), "--primitive-site", site_slug(website),
            "--cross-template-workflow-first", "--primitive-record",
            str(Path(runs) / f"{task_id}.primitive_retrieval.json"), "-o", str(runs),
        ]
    for config in configs:
        command.extend(("-c", config))
    return command


def verdicts(path):
    source = Path(path)
    if not source.exists() or not source.read_text(encoding="utf-8").strip():
        return {}
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            rows.extend(value if isinstance(value, list) else [value])
    return {str(row["task_id"]): row for row in rows}


def materialize(task, task_id, mode, runs, judge_jsonl):
    workspace = latest_workspace(runs, task_id)
    verdict = verdicts(judge_jsonl).get(task_id)
    label = verdict.get("predicted_label") if verdict else None
    valid = label in (0, 1, False, True)
    return {
        "task_id": task_id, "site": site_slug(task["website"]),
        "website": task["website"], "intent": task_text(task), "mode": mode,
        "score": float(int(label)) if valid else None,
        "correct": bool(label) if valid else None,
        "run_status": ("judged_success" if label == 1 else "judged_failure" if valid
                       else "evaluator_infrastructure_error"),
        "judge_mode": verdict.get("judge_mode") if verdict else None,
        "judge_record": verdict, "run_dir": str(workspace) if workspace else None,
    }


def compare(scratch, routed):
    complete = scratch.get("correct") is not None and routed.get("correct") is not None
    s, r = scratch.get("correct"), routed.get("correct")
    return {"task_id": scratch.get("task_id"), "complete": complete,
            "scratch_correct": s, "routed_correct": r,
            "win": bool(complete and r and not s), "loss": bool(complete and s and not r),
            "delta": (int(r) - int(s)) if complete else None}


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    solve = sub.add_parser("solve")
    solve.add_argument("task_id"); solve.add_argument("mode", choices=("scratch", "routed"))
    solve.add_argument("--dataset", required=True); solve.add_argument("--runs", required=True)
    solve.add_argument("--library", default="library")
    solve.add_argument("-c", "--config", action="append", default=[])
    solve.add_argument("--dry-run", action="store_true")
    mat = sub.add_parser("materialize")
    mat.add_argument("task_id"); mat.add_argument("mode", choices=("scratch", "routed"))
    mat.add_argument("--dataset", required=True); mat.add_argument("--runs", required=True)
    mat.add_argument("--judge-results", required=True); mat.add_argument("--output", required=True)
    pair = sub.add_parser("compare")
    pair.add_argument("--scratch", required=True); pair.add_argument("--routed", required=True)
    pair.add_argument("--output")
    args = parser.parse_args(argv)
    if args.command == "compare":
        result = compare(load_json(args.scratch), load_json(args.routed))
    else:
        tasks = tasks_by_id(args.dataset)
        if args.task_id not in tasks:
            raise SystemExit(f"unknown task_id: {args.task_id}")
        task = tasks[args.task_id]
        if args.command == "solve":
            command = solve_command(task, args.task_id, args.mode, args.runs,
                                    args.library, args.config)
            print(json.dumps({"command": command}, ensure_ascii=False, indent=2))
            return 0 if args.dry_run else subprocess.run(command).returncode
        result = materialize(task, args.task_id, args.mode, args.runs, args.judge_results)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    output = getattr(args, "output", None)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
