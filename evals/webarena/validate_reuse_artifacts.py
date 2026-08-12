#!/usr/bin/env python3
"""Fail-closed structural validation for reuse_split_v1 libraries and provenance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(split, sources, workflow_library, workflow_events, primitive_library):
    errors = []
    train_templates = {(site, row["intent_template_id"])
                       for site, rows in split["train"].items() for row in rows}
    test_templates = {(site, row["intent_template_id"])
                      for site, rows in split["test"].items() for row in rows}
    if train_templates & test_templates:
        errors.append("TRAIN/T2 template leakage")
    train_ids = {task_id for rows in split["train"].values() for row in rows
                 for task_id in row["build_task_ids"]}

    admitted_ids = set()
    for site, paths in sources.items():
        for path in paths:
            record = load(path)
            admitted_ids.add(record["task_id"])
            if record["task_id"] not in train_ids or record.get("correct") is not True:
                errors.append(f"invalid admitted source: {path}")
            if record.get("retrieved_primitives"):
                errors.append(f"contaminated TRAIN source: {path}")

    seen_workflows = set()
    for event in load(workflow_events):
        for skill_id in event.get("skill_ids") or []:
            key = (event["site"], event["template_id"])
            if key in seen_workflows:
                errors.append(f"multiple workflow skills for template: {key}")
            seen_workflows.add(key)
            root = Path(workflow_library) / event["site"] / skill_id
            if not (root / "skill.py").is_file() or not (root / "meta.json").is_file():
                errors.append(f"missing workflow artifact: {root}")
                continue
            code = (root / "skill.py").read_text(encoding="utf-8")
            if "audited_primitive" in code or "# primitive-source:" in code:
                errors.append(f"workflow imports primitive material: {root}")

    for site in split["train"]:
        root = Path(primitive_library) / site
        index_path = root / "final_candidate/index.json"
        if not index_path.is_file():
            errors.append(f"missing primitive final candidate: {site}")
            continue
        for required in (root / "batches", root / "pre_consolidation",
                         root / "consolidation", root / "final_candidate/primitive_pool.json"):
            if not required.exists():
                errors.append(f"missing primitive snapshot stage: {required}")
        index = load(index_path)
        for primitive in index.get("primitives") or []:
            workflow_ids = [item.get("workflow_id", "")
                            for item in primitive.get("source_evidence") or []]
            if not workflow_ids:
                errors.append(f"primitive lacks source evidence: {primitive.get('primitive_id')}")
            for workflow_id in workflow_ids:
                if workflow_id.startswith("task"):
                    try:
                        task_id = int(workflow_id.split("_", 1)[0][4:])
                    except ValueError:
                        errors.append(f"invalid source workflow id: {workflow_id}")
                    else:
                        if task_id not in admitted_ids:
                            errors.append(f"primitive cites non-admitted workflow: {workflow_id}")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--sources", required=True)
    ap.add_argument("--workflow-library", required=True)
    ap.add_argument("--workflow-events", required=True)
    ap.add_argument("--primitive-library", required=True)
    args = ap.parse_args()
    errors = validate(load(args.split), load(args.sources), args.workflow_library,
                      args.workflow_events, args.primitive_library)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
