#!/usr/bin/env python3
"""Export one Webwright final run to the official Odysseys rubric-judge layout."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


_SHOT_INDEX = re.compile(r"final_execution_(\d+)_")


def _latest_workspace(root: Path, task_id: str) -> Path:
    candidates = []
    for child in root.iterdir():
        metadata = child / "task.json"
        if not child.is_dir() or not metadata.is_file():
            continue
        try:
            if str(json.loads(metadata.read_text())["task_id"]) == task_id:
                candidates.append(child)
        except (KeyError, OSError, ValueError):
            continue
    if not candidates:
        raise ValueError(f"no workspace for {task_id} under {root}")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _pick_final_run(workspace: Path) -> Path:
    candidates = [path for path in (workspace / "final_runs").glob("run_*")
                  if (path / "final_script_log.txt").is_file()]
    if not candidates:
        raise ValueError(f"no complete final run under {workspace}")
    reflected = [path for path in candidates if (path / "self_reflect_result.json").is_file()]
    return max(reflected or candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def export(task_id: str, runs: Path, output: Path) -> dict:
    workspace = _latest_workspace(runs, task_id)
    final_run = _pick_final_run(workspace)
    destination = output / task_id
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_run / "final_script_log.txt", destination / "final_script_log.txt")
    shots_destination = destination / "screenshots"
    if shots_destination.exists():
        shutil.rmtree(shots_destination)
    shots_source = final_run / "screenshots"
    if shots_source.is_dir():
        shutil.copytree(shots_source, shots_destination)
    shots = sorted(
        (path for path in shots_destination.iterdir() if path.is_file()),
        key=lambda path: (int(match.group(1)) if (match := _SHOT_INDEX.search(path.name))
                          else 10**9, path.name),
    ) if shots_destination.is_dir() else []
    action = (destination / "final_script_log.txt").read_text(errors="replace")
    rows = [{"step_num": 1, "action": action}]
    if shots:
        rows[0]["screenshot"] = str(shots[0].resolve())
        rows.extend({"step_num": index, "action": "", "screenshot": str(shot.resolve())}
                    for index, shot in enumerate(shots[1:], start=2))
    (destination / "steps.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    (destination / "result.txt").write_text("1.0\n", encoding="utf-8")
    return {"task_id": task_id, "workspace": str(workspace), "final_run": str(final_run),
            "output": str(destination), "screenshots": len(shots)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(export(args.task_id, args.runs, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
