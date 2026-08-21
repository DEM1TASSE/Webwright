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
from cross_task_eval import (  # noqa: E402
    configure_router_model, credentials_for, prepare_workflow_hint,
    retrieve_direct_primitives,
)
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
    ap.add_argument(
        "--deployment-config",
        help="Optional deployment config used to mirror runner-provided credential bindings.",
    )
    ap.add_argument("--output", required=True)
    ap.add_argument("--sites", nargs="*", help="Optional site subset for resumable parallel audit")
    args = ap.parse_args()
    split, dataset = load(args.split), load(args.dataset)
    deployment = load(args.deployment_config) if args.deployment_config else None
    validate_no_leakage(split)
    tasks = {row["task_id"]: row for row in dataset}
    skills = workflow_map(args.workflow_events)
    configure_router_model(args.model_config)
    selected_sites = set(args.sites or split["train"])

    rows = []
    for site, task_type, template_id, task_id in build_jobs(split, "t1"):
        if site not in selected_sites:
            continue
        skill_id = skills.get((site, template_id))
        rows.append({
            "partition": "t1", "arm": "workflow", "site": site,
            "template_id": template_id, "task_id": task_id,
            "decision": "use" if skill_id else "skip", "skill_id": skill_id,
            "reason": "exact template skill" if skill_id else "no three-gold workflow skill",
        })

    for site, task_type, template_id, task_id in build_jobs(split, "t2"):
        if site not in selected_sites:
            continue
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
            runtime_context = {
                "available_bindings": ["runtime.base_url", "runtime.browser_page"],
                "available_states": [],
                "task_type": task_type,
            }
            if deployment and credentials_for(task, deployment):
                runtime_context["available_bindings"].extend([
                    "runtime.credentials.username", "runtime.credentials.password",
                ])
            primitive = retrieve_direct_primitives(
                task["intent"], args.primitive_library, site=site, max_primitives=5,
                runtime_context=runtime_context,
            )
            rows.append({
                "partition": "t2", "arm": "primitive", "site": site,
                "template_id": template_id, "task_id": task_id,
                "decision": primitive.decision,
                "primitive_ids": [item["primitive_id"] for item in primitive.primitives],
                "reason": primitive.reason, "remaining_gap": primitive.remaining_gap,
                "late_bind_required": bool(
                    (primitive.proposal or {}).get("late_bind_required")
                ),
                "late_bind_reason": str(
                    (primitive.proposal or {}).get("late_bind_reason") or ""
                ),
                "contract_verdict": primitive.contract_verdict,
            })
        except Exception as error:
            rows.append({"partition": "t2", "arm": "primitive", "site": site,
                         "template_id": template_id, "task_id": task_id,
                         "decision": "error", "error": str(error)})
        print(json.dumps(rows[-2:], ensure_ascii=False), flush=True)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = Counter((row["partition"], row["arm"], row["decision"]) for row in rows)
    print(json.dumps({"records": len(rows), "counts": {"/".join(k): v for k, v in counts.items()}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
