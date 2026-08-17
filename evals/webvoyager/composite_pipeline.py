#!/usr/bin/env python3
"""Build, run, judge, and summarize composed WebVoyager tasks."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from pipeline import latest_workspace, task_text, task_website, tasks_by_id


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render_task(bundle, tasks):
    rows = [tasks[task_id] for task_id in bundle["task_ids"]]
    sites = []
    for row in rows:
        website = task_website(row)
        if website not in sites:
            sites.append(website)
    lines = [
        f"Complete all {len(rows)} independent web tasks below. Do not stop after only one task.",
        "You may navigate between the listed websites. Preserve evidence for every task.",
        "In the final answer, use one section headed exactly `SUBTASK <task-id>` per task.",
        "During final execution, save at least one evidence screenshot per task and include the",
        "normalized task id in its filename (example: GitHub--15 becomes github_15).",
        "",
    ]
    for index, (task_id, row) in enumerate(zip(bundle["task_ids"], rows), 1):
        lines.extend((f"{index}. SUBTASK {task_id}", f"Website: {task_website(row)}",
                      f"Instruction: {task_text(row)}", ""))
    return {
        "web_name": " + ".join(dict.fromkeys(str(row.get("web_name") or "") for row in rows)),
        "id": bundle["id"], "ques": "\n".join(lines).rstrip(), "web": sites[0],
        "scope": bundle["scope"], "subtask_ids": bundle["task_ids"], "websites": sites,
    }


def build_dataset(tasks_file, spec_file, output):
    tasks, spec = tasks_by_id(tasks_file), load_json(spec_file)
    seen = set()
    records = []
    for bundle in spec["bundles"]:
        if bundle["id"] in seen:
            raise ValueError(f"duplicate bundle id: {bundle['id']}")
        seen.add(bundle["id"])
        missing = [task_id for task_id in bundle["task_ids"] if task_id not in tasks]
        if missing:
            raise ValueError(f"{bundle['id']} has unknown tasks: {missing}")
        sites = {task_website(tasks[task_id]) for task_id in bundle["task_ids"]}
        expected = "same_site" if len(sites) == 1 else "cross_site"
        if bundle["scope"] != expected:
            raise ValueError(f"{bundle['id']} scope should be {expected}")
        records.append(render_task(bundle, tasks))
    target = Path(output); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
                      encoding="utf-8")
    return records


def normalize_id(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def judgeable_run(workspace):
    from webwright.skill_factory.om2w_eval import load_screenshots
    from webwright.skill_factory.webvoyager_eval import load_final_response

    root = Path(workspace) / "final_runs"
    candidates = sorted(
        (path for path in root.iterdir() if path.is_dir() and path.name.startswith("run_")),
        key=lambda path: int(path.name.rsplit("_", 1)[-1]), reverse=True,
    ) if root.is_dir() else []
    for run in candidates:
        screenshots = load_screenshots(run / "screenshots")
        answer = load_final_response(run)
        if not answer:
            log = run / "final_script_log.txt"
            text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
            match = re.search(r"(?im)^SUBTASK\s+[^\n]+(?:\n|$)", text)
            if match:
                answer = text[match.start():].strip()
        if screenshots and answer:
            return run, screenshots, answer
    raise RuntimeError(f"no judgeable final run under {root}")


def select_evidence(screenshots, task_id, max_images):
    token = normalize_id(task_id)
    named = [path for path in screenshots if token in normalize_id(Path(path).stem)]
    selected = named if named else screenshots
    return selected[-max_images:], "task_named" if named else "all_run_fallback"


def judge_bundle(bundle, original_tasks, runs, engine, mode, repetitions, max_images,
                 subtask_ids=None):
    from webwright.skill_factory.webvoyager_eval import evaluate_evidence

    workspace = latest_workspace(runs, bundle["id"])
    if workspace is None:
        raise RuntimeError(f"no workspace for {bundle['id']}")
    run, screenshots, answer = judgeable_run(workspace)
    records = []
    for position, task_id in enumerate(bundle["task_ids"], 1):
        if subtask_ids and task_id not in subtask_ids:
            continue
        row = original_tasks[task_id]
        selected, selection = select_evidence(screenshots, task_id, max_images)
        task = {**row, "task": task_text(row), "website": task_website(row)}
        record = evaluate_evidence(
            f"{bundle['id']}::{task_id}", task, run, selected, answer, engine,
            mode=mode, repetitions=repetitions,
            judge_mode="WebVoyager_composite_per_original_subtask",
        )
        record.update({
            "bundle_id": bundle["id"], "scope": bundle["scope"],
            "bundle_size": len(bundle["task_ids"]), "subtask_id": task_id,
            "subtask_position": position, "evidence_selection": selection,
            "all_run_screenshot_count": len(screenshots),
        })
        records.append(record)
    return records


def execution_failure_records(bundle, original_tasks, runs, mode, reason):
    """Materialize an agent execution failure as failed WebVoyager subtasks."""
    workspace = latest_workspace(runs, bundle["id"])
    return [{
        "task_id": f"{bundle['id']}::{task_id}", "bundle_id": bundle["id"],
        "scope": bundle["scope"], "bundle_size": len(bundle["task_ids"]),
        "subtask_id": task_id, "subtask_position": position,
        "web_name": original_tasks[task_id].get("web_name"),
        "website": task_website(original_tasks[task_id]),
        "task": task_text(original_tasks[task_id]), "mode": mode,
        "judge_mode": "WebVoyager_composite_execution_failure",
        "predicted_label": 0, "judge_labels": [], "judge_repetitions": 0,
        "failure_reason": str(reason), "workspace": str(workspace) if workspace else None,
    } for position, task_id in enumerate(bundle["task_ids"], 1)]


def summarize(records, baseline_accuracy=None):
    groups = defaultdict(list)
    bundles = defaultdict(list)
    for row in records:
        groups[(row["scope"], row["bundle_size"])].append(row)
        bundles[row["bundle_id"]].append(row)
    strata = []
    for (scope, size), rows in sorted(groups.items()):
        valid = [row for row in rows if row.get("predicted_label") in (0, 1)]
        passed = sum(int(row["predicted_label"]) for row in valid)
        bundle_rows = [value for value in bundles.values()
                       if value and value[0]["scope"] == scope and value[0]["bundle_size"] == size]
        all_pass = sum(bool(value) and all(row.get("predicted_label") == 1 for row in value)
                       for value in bundle_rows)
        accuracy = passed / len(valid) if valid else None
        strata.append({
            "scope": scope, "bundle_size": size, "subtask_trials": len(rows),
            "judged_subtasks": len(valid), "passed_subtasks": passed,
            "micro_accuracy": accuracy,
            "delta_from_single_baseline": (accuracy - baseline_accuracy
                                           if accuracy is not None and baseline_accuracy is not None
                                           else None),
            "bundles": len(bundle_rows), "all_subtasks_passed_bundles": all_pass,
            "all_pass_rate": all_pass / len(bundle_rows) if bundle_rows else None,
        })
    return {"single_task_baseline_accuracy": baseline_accuracy, "strata": strata,
            "bundle_results": {
                bundle_id: {"passed": sum(row.get("predicted_label") == 1 for row in rows),
                            "total": len(rows),
                            "all_pass": all(row.get("predicted_label") == 1 for row in rows)}
                for bundle_id, rows in sorted(bundles.items())}}


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--tasks-file", required=True); build.add_argument("--spec", required=True)
    build.add_argument("--output", required=True)
    solve = sub.add_parser("solve")
    solve.add_argument("bundle_id"); solve.add_argument("--dataset", required=True)
    solve.add_argument("--runs", required=True); solve.add_argument("-c", "--config", action="append", default=[])
    solve.add_argument("--dry-run", action="store_true")
    judge = sub.add_parser("judge")
    judge.add_argument("--tasks-file", required=True); judge.add_argument("--spec", required=True)
    judge.add_argument("--runs", required=True); judge.add_argument("--output", required=True)
    judge.add_argument("--model", default="gpt-4o")
    judge.add_argument("--endpoint", default=os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1/responses"))
    judge.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""))
    judge.add_argument("--timeout", type=int, default=600); judge.add_argument("--repetitions", type=int, default=3)
    judge.add_argument("--max-images", type=int, default=30); judge.add_argument("--mode", default="scratch")
    judge.add_argument("--bundle-id", action="append",
                       help="Judge only these bundle IDs; repeat for multiple bundles.")
    judge.add_argument("--subtask-id", action="append",
                       help="Within selected bundles, judge only these original task IDs.")
    report = sub.add_parser("summarize")
    report.add_argument("--results", required=True, action="append",
                        help="Result JSONL; repeat to apply later corrected records as overrides.")
    report.add_argument("--spec", required=True)
    report.add_argument("--output")
    args = parser.parse_args(argv)

    if args.command == "build":
        result = build_dataset(args.tasks_file, args.spec, args.output)
        print(json.dumps({"output": args.output, "bundles": len(result)}, indent=2)); return 0
    if args.command == "solve":
        from pipeline import solve_command
        tasks = tasks_by_id(args.dataset)
        if args.bundle_id not in tasks:
            raise SystemExit(f"unknown bundle_id: {args.bundle_id}")
        command = solve_command(tasks[args.bundle_id], args.bundle_id, "scratch", args.runs,
                                "library", args.config)
        print(json.dumps({"command": command}, ensure_ascii=False, indent=2))
        return 0 if args.dry_run else subprocess.run(command).returncode
    if args.command == "judge":
        from webwright.skill_factory.om2w_eval import ResponsesEngine
        if not args.api_key:
            raise SystemExit("set OPENAI_API_KEY or pass --api-key")
        tasks, spec = tasks_by_id(args.tasks_file), load_json(args.spec)
        output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
        existing = set()
        if output.is_file():
            existing = {json.loads(line)["bundle_id"] for line in output.read_text().splitlines()
                        if line.strip()}
        engine = ResponsesEngine(args.model, args.api_key, args.endpoint, args.timeout)
        with output.open("a", encoding="utf-8") as stream:
            for bundle in spec["bundles"]:
                if args.bundle_id and bundle["id"] not in set(args.bundle_id):
                    continue
                if bundle["id"] in existing:
                    continue
                try:
                    records = judge_bundle(bundle, tasks, args.runs, engine, args.mode,
                                           args.repetitions, args.max_images,
                                           set(args.subtask_id or []))
                except RuntimeError as exc:
                    records = execution_failure_records(bundle, tasks, args.runs, args.mode, exc)
                for record in records:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n"); stream.flush()
                print(f"{bundle['id']}: {sum(r['predicted_label'] == 1 for r in records)}/{len(records)}")
        return 0
    by_task_id = {}
    for result_path in args.results:
        for line in Path(result_path).read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                by_task_id[record["task_id"]] = record
    records = list(by_task_id.values())
    baseline = load_json(args.spec).get("single_task_baseline", {}).get("accuracy")
    result = summarize(records, baseline)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end=""); return 0


if __name__ == "__main__":
    raise SystemExit(main())
