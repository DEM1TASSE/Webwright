#!/usr/bin/env python3
"""Retrieval-only audit for frozen T1 workflows and T2 workflow/primitive routing."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cross_task_eval import configure_router_model, prepare_workflow_hint  # noqa: E402
from run_reuse_eval import build_jobs, workflow_map  # noqa: E402


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_no_leakage(split):
    train_templates = {(site, row["intent_template_id"])
                       for site, rows in split["train"].items() for row in rows}
    test_templates = {(site, row["intent_template_id"])
                      for site, rows in split["test"].items() for row in rows}
    overlap = train_templates & test_templates
    if overlap:
        raise ValueError(f"TRAIN/T2 template leakage: {sorted(overlap)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--workflow-library", required=True)
    ap.add_argument("--workflow-events", required=True)
    ap.add_argument("--primitive-library", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    split, dataset = load(args.split), load(args.dataset)
    validate_no_leakage(split)
    tasks = {row["task_id"]: row for row in dataset}
    skills = workflow_map(args.workflow_events)
    configure_router_model(args.model_config)

    rows = []
    for site, template_id, task_id in build_jobs(split, "t1"):
        skill_id = skills.get((site, template_id))
        rows.append({
            "partition": "t1", "arm": "workflow", "site": site,
            "template_id": template_id, "task_id": task_id,
            "decision": "use" if skill_id else "skip", "skill_id": skill_id,
            "reason": "exact template skill" if skill_id else "no three-gold workflow skill",
        })

    from webwright.skill_factory.audited_primitive_retrieve import retrieve_audited_primitives
    for site, template_id, task_id in build_jobs(split, "t2"):
        task = tasks[task_id]
        try:
            workflow = prepare_workflow_hint(task, Path(args.workflow_library) / site)
            rows.append({
                "partition": "t2", "arm": "workflow", "site": site,
                "template_id": template_id, "task_id": task_id,
                "decision": workflow["decision"], "skill_id": workflow["skill_id"],
                "reason": workflow["reason"],
            })
        except Exception as error:
            rows.append({"partition": "t2", "arm": "workflow", "site": site,
                         "template_id": template_id, "task_id": task_id,
                         "decision": "error", "error": str(error)})
        try:
            primitive = retrieve_audited_primitives(
                task["intent"], args.primitive_library, site=site, max_primitives=5,
            )
            rows.append({
                "partition": "t2", "arm": "primitive", "site": site,
                "template_id": template_id, "task_id": task_id,
                "decision": primitive.decision,
                "primitive_ids": [item["primitive_id"] for item in primitive.primitives],
                "reason": primitive.reason, "remaining_gap": primitive.remaining_gap,
            })
        except Exception as error:
            rows.append({"partition": "t2", "arm": "primitive", "site": site,
                         "template_id": template_id, "task_id": task_id,
                         "decision": "error", "error": str(error)})
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(rows[-2:], ensure_ascii=False), flush=True)

    counts = Counter((row["partition"], row["arm"], row["decision"]) for row in rows)
    print(json.dumps({"records": len(rows), "counts": {"/".join(k): v for k, v in counts.items()}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
