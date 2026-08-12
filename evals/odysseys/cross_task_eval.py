#!/usr/bin/env python3
"""Run an Odysseys task scratch or with independently gated site primitives."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

from site_primitives import (
    load_segments, render_multisite_hint, route_site_segments,
    write_routing_manifest,
)


def load_tasks(path: str | Path) -> dict[str, dict]:
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8"))
    return {str(row["task_id"]): row for row in raw}


def configure_router(model_config: str | Path) -> None:
    from webwright.skill_factory.llm import configure_llm
    config = yaml.safe_load(Path(model_config).read_text(encoding="utf-8")) or {}
    if not isinstance(config.get("model"), dict):
        raise ValueError(f"{model_config}: missing model configuration")
    configure_llm(config["model"])


def build_prompt(task: dict, mode: str, *, segments_path=None, library=None,
                 records_dir=None, model_config=None) -> tuple[str, list]:
    text = str(task.get("confirmed_task") or task.get("task") or "").strip()
    if mode == "scratch":
        return text, []
    if not all((segments_path, library, records_dir, model_config)):
        raise ValueError("primitive mode requires segments, library, records-dir and model-config")
    configure_router(model_config)
    segments = load_segments(segments_path, str(task["task_id"]))
    routed = route_site_segments(segments, library, records_dir)
    return render_multisite_hint(routed) + "\n" + text, routed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("mode", choices=("scratch", "primitive"))
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--runs", required=True)
    parser.add_argument("--segments")
    parser.add_argument("--library")
    parser.add_argument("--model-config")
    parser.add_argument("-c", "--config", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    task = load_tasks(args.tasks).get(args.task_id)
    if task is None:
        raise SystemExit(f"unknown task_id: {args.task_id}")
    records = Path(args.runs) / f"{args.task_id}.site_retrievals"
    prompt, routed = build_prompt(
        task, args.mode, segments_path=args.segments, library=args.library,
        records_dir=records, model_config=args.model_config,
    )
    if routed:
        write_routing_manifest(
            Path(args.runs) / f"{args.task_id}.site_routing.json", args.task_id, routed,
        )
    command = [
        sys.executable, "-m", "webwright.run.cli", "main", "-t", prompt,
        "--task-id", f"{args.task_id}_{args.mode}",
        "--start-url", str(task.get("website") or "https://www.google.com"),
        "-o", args.runs,
    ]
    configs = list(args.config)
    if configs and not any(Path(item).name == "base.yaml" for item in configs):
        configs.insert(0, "base.yaml")
    for config in configs:
        command.extend(("-c", config))
    print(json.dumps({
        "task_id": args.task_id,
        "mode": args.mode,
        "site_segments": len(routed),
        "command": command,
    }, ensure_ascii=False, indent=2))
    return 0 if args.dry_run else subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
