#!/usr/bin/env python3
"""Build a generated-only primitive catalog from clean gold-admitted run records."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from webwright.skill_factory.llm import llm_json
from webwright.skill_factory.primitive_catalog import PrimitiveCatalog
from webwright.skill_factory.primitive_update import apply_updates, propose_updates


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clean_workflow(record_path, dataset):
    record = load(record_path)
    if record.get("score") != 1.0 or record.get("correct") is not True:
        raise ValueError(f"{record_path}: source is not gold-admitted")
    if record.get("retrieved_primitives"):
        raise ValueError(f"{record_path}: source consumed primitive material")
    task_id = record["task_id"]
    task = next((x for x in dataset if x["task_id"] == task_id), None)
    if task is None:
        raise ValueError(f"{record_path}: task {task_id} missing from dataset")
    run_dir = Path(record["run_dir"])
    code_path = run_dir / "final_script.py"
    if not code_path.exists():
        raise ValueError(f"{record_path}: final_script.py missing")
    workflow_id = f"task{task_id}_t{task['intent_template_id']}"
    return {
        "id": workflow_id,
        "task_id": task_id,
        "template_id": task["intent_template_id"],
        "intent": task["intent"],
        "site": task["sites"][0],
        "code": code_path.read_text(encoding="utf-8"),
        "record_path": str(record_path),
        "run_dir": str(run_dir),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    manifest = load(args.manifest)
    dataset = load(args.dataset)
    by_site = defaultdict(list)
    for declared_site, paths in manifest.items():
        for path in paths:
            workflow = clean_workflow(path, dataset)
            if workflow["site"] != declared_site:
                raise ValueError(
                    f"{path}: manifest site {declared_site} != task site {workflow['site']}"
                )
            by_site[declared_site].append(workflow)

    report = {"library": args.library, "sites": {}}
    for site, workflows in sorted(by_site.items()):
        templates = {x["template_id"] for x in workflows}
        if len(templates) < 2:
            raise ValueError(f"{site}: generated ADD requires at least two templates")
        catalog = PrimitiveCatalog(args.library, site)
        raw_proposals = []

        def proposer(system, user):
            raw = llm_json(system, user, max_tokens=16000)
            raw_proposals.append(raw)
            return raw

        operations = propose_updates(
            site=site,
            new_workflow=workflows[-1],
            peer_workflows=workflows[:-1],
            catalog=catalog,
            llm_fn=proposer,
        )
        gold_ids = {x["id"] for x in workflows}
        result = apply_updates(
            catalog,
            operations,
            gold_workflows=gold_ids,
            review_path=Path(args.report).with_suffix(f".{site}.review.jsonl"),
        )
        report["sites"][site] = {
            "source_workflows": [
                {
                    "id": x["id"],
                    "task_id": x["task_id"],
                    "template_id": x["template_id"],
                    "record_path": x["record_path"],
                }
                for x in workflows
            ],
            "raw_proposals": raw_proposals,
            "operations": [vars(x) for x in operations],
            "applied": result.applied,
            "reviewed": result.reviewed,
            "rejected": result.rejected,
            "active_primitives": [
                {
                    "primitive_id": x.primitive_id,
                    "content_hash": x.content_hash,
                    "source_templates": x.source_templates,
                    "source_workflows": x.source_workflows,
                }
                for x in catalog.list()
            ],
        }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
