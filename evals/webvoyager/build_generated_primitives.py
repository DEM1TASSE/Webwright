#!/usr/bin/env python3
"""Build a site primitive catalog from judge-admitted WebVoyager source runs."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from webwright.skill_factory.om2w_eval import discover_task_dirs, latest_run
from webwright.skill_factory.webvoyager_eval import load_task_map


_COMMON_PATH = Path(__file__).parents[1] / "om2w" / "build_generated_primitives.py"
_SPEC = importlib.util.spec_from_file_location("cross_task_primitive_builder", _COMMON_PATH)
_COMMON = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_COMMON)
build = _COMMON.build
load_jsonl = _COMMON.load_jsonl
parse_sources = _COMMON.parse_sources
slug = _COMMON.slug


def admitted_workflows(dataset_path, runs_root, judge_path, sources):
    tasks = load_task_map(dataset_path)
    verdicts = {str(row["task_id"]): row for row in load_jsonl(judge_path)}
    workspaces = discover_task_dirs(runs_root, set(sources))
    workflows = []
    for task_id, family in sources.items():
        if verdicts.get(task_id, {}).get("predicted_label") != 1:
            raise ValueError(f"{task_id}: source is not judge-admitted")
        task = tasks.get(task_id)
        if task is None:
            raise ValueError(f"{task_id}: missing from dataset")
        workspace = workspaces.get(task_id)
        run = latest_run(workspace) if workspace else None
        code_path = run / "final_script.py" if run else None
        if code_path is None or not code_path.is_file():
            raise ValueError(f"{task_id}: latest final run has no final_script.py")
        website = task["website"]
        workflows.append({
            "id": f"task{task_id}_{family}", "task_id": task_id,
            "template_id": family, "intent": task["task"],
            "site": slug(website), "website": website,
            "code": code_path.read_text(encoding="utf-8"),
            "run_dir": str(run), "judge_record": verdicts[task_id],
        })
    return workflows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True); parser.add_argument("--runs", required=True)
    parser.add_argument("--judge-results", required=True); parser.add_argument("--library", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--source", action="append", required=True,
                        help="Judge-admitted TASK_ID=FAMILY_ID; repeat for each source.")
    args = parser.parse_args(argv)
    workflows = admitted_workflows(args.dataset, args.runs, args.judge_results,
                                   parse_sources(args.source))
    print(json.dumps(build(workflows, args.library, args.report), ensure_ascii=False))


if __name__ == "__main__":
    main()
