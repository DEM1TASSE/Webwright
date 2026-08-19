#!/usr/bin/env python3
"""Extract auditable scratch/primitive trajectory evidence for selected tasks."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


URL_RE = re.compile(r"https?://[^\s'\"`]+")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def result_path(root: Path, arm: str, site: str, task_id: int) -> Path:
    return root / "t2" / arm / site / f"task{task_id}_{arm}.json"


def model_turns(run_dir: Path) -> list[dict]:
    path = run_dir / "raw_responses.jsonl"
    turns = []
    if not path.exists():
        return turns
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
            if event.get("source") != "model" or event.get("event") != "raw_text":
                continue
            payload = json.loads(event.get("raw_text") or "{}")
        except (TypeError, ValueError):
            continue
        command = str(payload.get("bash_command") or "")
        turns.append({
            "timestamp": event.get("timestamp"),
            "thought": str(payload.get("thought") or ""),
            "command": command,
            "done": bool(payload.get("done")),
            "urls": sorted(set(URL_RE.findall(command))),
        })
    return turns


def artifact(path: Path):
    try:
        return load(path)
    except (OSError, ValueError):
        return None


def arm_record(result: dict) -> dict:
    run_dir = Path(result["run_dir"])
    turns = model_turns(run_dir)
    commands = "\n".join(turn["command"] for turn in turns)
    primitive_ids = [
        row.get("primitive_id") for row in result.get("retrieved_primitives") or []
        if row.get("primitive_id")
    ]
    return {
        "correct": result.get("correct"),
        "score": result.get("score"),
        "steps": result.get("steps"),
        "run_status": result.get("run_status"),
        "answer": result.get("answer"),
        "run_dir": str(run_dir),
        "route_decision": result.get("route_decision"),
        "route_reason": result.get("route_reason"),
        "route_remaining_gap": result.get("route_remaining_gap") or [],
        "retrieved_primitives": primitive_ids,
        "incorporated_primitives": result.get("code_incorporated_primitives") or [],
        "execution_trace": result.get("primitive_execution_trace") or [],
        "agent_response": artifact(run_dir / "agent_response.json"),
        "final_state": artifact(run_dir / "final_state.json"),
        "turn_count": len(turns),
        "thoughts": [turn["thought"] for turn in turns],
        "commands": [turn["command"] for turn in turns],
        "observed_urls": sorted(set(URL_RE.findall(commands))),
        "strategy_signals": {
            "mentions_primitive": "primitive" in ("\n".join(
                turn["thought"] + "\n" + turn["command"] for turn in turns
            )).lower(),
            "uses_source_marker": "primitive-source:" in commands,
            "uses_direct_http": bool(re.search(r"\b(requests|httpx|curl\b|urllib)", commands)),
            "uses_playwright": "playwright" in commands.lower(),
            "searches_workspace": bool(re.search(r"\b(rg|grep|find)\b.*(primitive|skill|runs)", commands)),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = []
    for case in load(args.manifest)["cases"]:
        task_id = int(case["task_id"])
        primitive_matches = list((args.results_root / "t2" / "primitive").glob(
            f"*/task{task_id}_primitive.json"
        ))
        if len(primitive_matches) != 1:
            raise SystemExit(f"task {task_id}: expected one primitive result, found {len(primitive_matches)}")
        primitive_result = load(primitive_matches[0])
        site = primitive_result["site"]
        scratch_result = load(result_path(args.results_root, "scratch", site, task_id))
        cases.append({
            **case,
            "site": site,
            "task_type": primitive_result.get("task_type"),
            "intent": primitive_result.get("task_intent"),
            "scratch": arm_record(scratch_result),
            "primitive": arm_record(primitive_result),
        })

    payload = {"manifest": str(args.manifest), "cases": cases}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
