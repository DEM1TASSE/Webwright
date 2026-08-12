#!/usr/bin/env python3
"""Export a Webwright final run to the official Odysseys judge layout."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


SHOT_INDEX = re.compile(r"final_execution_(\d+)_")


def task_identity(workspace: Path) -> str:
    value = str(json.loads((workspace / "task.json").read_text())["task_id"])
    for suffix in ("_scratch", "_primitive"):
        if value.endswith(suffix):
            return value[:-len(suffix)]
    return value


def task_mode(workspace: Path) -> str | None:
    value = str(json.loads((workspace / "task.json").read_text())["task_id"])
    for mode in ("scratch", "primitive"):
        if value.endswith(f"_{mode}"):
            return mode
    return None


def latest_workspace(root: Path, task_id: str, *, mode: str | None = None) -> Path:
    candidates = [child for child in root.iterdir() if child.is_dir()
                  and (child / "task.json").is_file() and task_identity(child) == task_id
                  and (mode is None or task_mode(child) == mode)]
    if not candidates:
        suffix = f" in {mode} mode" if mode else ""
        raise ValueError(f"no workspace for {task_id}{suffix} under {root}")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def pick_final_run(workspace: Path, *, allow_incomplete: bool = False,
                   require_self_reflection_pass: bool = False) -> Path:
    candidates = [path for path in (workspace / "final_runs").glob("run_*")
                  if (path / "final_script_log.txt").is_file()]
    reflected = []
    successful = []
    for path in candidates:
        try:
            result = json.loads((path / "self_reflect_result.json").read_text())
            if result.get("predicted_label") in (0, 1, False, True):
                reflected.append(path)
            if result.get("predicted_label") in (1, True):
                successful.append(path)
        except (OSError, ValueError):
            pass
    if successful:
        return max(successful, key=lambda path: (path.stat().st_mtime_ns, path.name))
    if not require_self_reflection_pass and reflected:
        return max(reflected, key=lambda path: (path.stat().st_mtime_ns, path.name))
    if not candidates:
        raise ValueError(f"no executed final run under {workspace}")
    if not allow_incomplete:
        raise ValueError(
            f"no {'self-reflection-passing' if require_self_reflection_pass else 'self-reflected'} "
            f"final run under {workspace}; "
            "refusing to export an incomplete trajectory"
        )
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def export(task_id: str, runs: Path, output: Path, *, allow_incomplete: bool = False,
           require_self_reflection_pass: bool = False, mode: str | None = None) -> dict:
    workspace = latest_workspace(runs, task_id, mode=mode)
    final_run = pick_final_run(
        workspace, allow_incomplete=allow_incomplete,
        require_self_reflection_pass=require_self_reflection_pass,
    )
    destination = output / task_id
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_run / "final_script_log.txt", destination / "final_script_log.txt")
    shots_destination = destination / "screenshots"
    if shots_destination.exists():
        shutil.rmtree(shots_destination)
    shots_source = final_run / "screenshots"
    if shots_source.is_dir():
        shutil.copytree(shots_source, shots_destination)
    shots = sorted(shots_destination.glob("*.png"), key=lambda path: (
        int(match.group(1)) if (match := SHOT_INDEX.search(path.name)) else 10**9, path.name,
    )) if shots_destination.is_dir() else []
    action = (destination / "final_script_log.txt").read_text(errors="replace")
    rows = [{"step_num": 1, "action": action}]
    if shots:
        rows[0]["screenshot"] = str(shots[0].resolve())
        rows.extend({"step_num": index, "action": "", "screenshot": str(shot.resolve())}
                    for index, shot in enumerate(shots[1:], start=2))
    (destination / "steps.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    (destination / "result.txt").write_text("1.0\n", encoding="utf-8")
    return {"task_id": task_id, "workspace": str(workspace), "final_run": str(final_run),
            "output": str(destination), "screenshots": len(shots)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--mode", choices=("scratch", "primitive"),
        help="Select one arm when scratch and primitive workspaces share --runs.",
    )
    parser.add_argument(
        "--allow-incomplete", action="store_true",
        help="Debug only: export the latest run even when self-reflection did not pass",
    )
    parser.add_argument(
        "--require-self-reflection-pass", action="store_true",
        help="Require predicted_label=1 instead of merely requiring a completed reflection",
    )
    args = parser.parse_args(argv)
    print(json.dumps(export(
        args.task_id, args.runs, args.output, allow_incomplete=args.allow_incomplete,
        require_self_reflection_pass=args.require_self_reflection_pass, mode=args.mode,
    ), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
