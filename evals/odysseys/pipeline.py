#!/usr/bin/env python3
"""Minimal Webwright runner for an Odysseys task (no OSWorld required)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path


_WV_PATH = Path(__file__).parents[1] / "webvoyager" / "pipeline.py"
_SPEC = importlib.util.spec_from_file_location("webvoyager_pipeline", _WV_PATH)
_WV = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_WV)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--runs", required=True)
    parser.add_argument("-c", "--config", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    tasks = _WV.tasks_by_id(args.tasks)
    if args.task_id not in tasks:
        raise SystemExit(f"unknown task_id: {args.task_id}")
    task = tasks[args.task_id]
    command = _WV.solve_command(
        task, args.task_id, "scratch", args.runs, "", args.config,
    )
    print(json.dumps({
        "task_id": args.task_id,
        "level": task.get("level"),
        "reference_length": task.get("reference_length"),
        "command": command,
    }, ensure_ascii=False, indent=2))
    return 0 if args.dry_run else subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
