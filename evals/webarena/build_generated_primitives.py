#!/usr/bin/env python3
"""Build a generated-only primitive catalog from clean gold-admitted run records."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from webwright.skill_factory.llm import llm_json
from webwright.skill_factory.primitive_catalog import PrimitiveCatalog
from webwright.skill_factory.primitive_update import (
    apply_updates,
    propose_updates,
    verify_operations_evidence,
)


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

    report = {"library": args.library, "build_mode": "incremental", "sites": {}}
    for site, workflows in sorted(by_site.items()):
        if not workflows:
            raise ValueError(f"{site}: no gold-admitted workflows")
        catalog = PrimitiveCatalog(args.library, site)
        rounds = []
        all_operations = []
        all_applied, all_reviewed, all_rejected = [], [], []
        seen = []
        for workflow in workflows:
            evidence_map = {x["id"]: x for x in [*seen, workflow]}
            proposal_attempts = []
            proposal_workflow = workflow
            operations = []
            for attempt in range(1, 4):
                raw_proposals = []

                def proposer(system, user):
                    raw = llm_json(system, user, max_tokens=16000)
                    raw_proposals.append(raw)
                    return raw

                operations = propose_updates(
                    site=site,
                    new_workflow=proposal_workflow,
                    peer_workflows=seen,
                    catalog=catalog,
                    llm_fn=proposer,
                )
                operations = verify_operations_evidence(
                    operations, evidence_map, active_primitives=catalog.list()
                )
                evidence_errors = [
                    {
                        "primitive_id": operation.primitive_id,
                        "error": operation.evidence_verification_reason,
                    }
                    for operation in operations
                    if operation.op.upper() in {"ADD", "MODIFY"}
                    and operation.evidence_verified is not True
                ]
                proposal_attempts.append({
                    "attempt": attempt,
                    "raw_proposal": raw_proposals[0] if raw_proposals else None,
                    "evidence_errors": evidence_errors,
                })
                if not evidence_errors:
                    break
                proposal_workflow = {
                    **workflow,
                    "evidence_gate_feedback": evidence_errors,
                    "retry_instruction": (
                        "Correct every evidence error using exact code from the supplied workflows. "
                        "Narrow the capability to the shared implementation core or return "
                        "NO_CHANGE; never invent provenance."
                    ),
                }
            admitted_ids = {x["id"] for x in [*seen, workflow]}
            result = apply_updates(
                catalog,
                operations,
                gold_workflows=admitted_ids,
                workflow_evidence=evidence_map,
                review_path=Path(args.report).with_suffix(f".{site}.review.jsonl"),
            )
            round_record = {
                "workflow_id": workflow["id"],
                "template_id": workflow["template_id"],
                "decision": "UPDATE" if operations else "NO_CHANGE",
                "raw_proposal": proposal_attempts[-1]["raw_proposal"],
                "proposal_attempts": proposal_attempts,
                "operations": [vars(x) for x in operations],
                "applied": result.applied,
                "reviewed": result.reviewed,
                "rejected": result.rejected,
            }
            rounds.append(round_record)
            all_operations.extend(operations)
            all_applied.extend(result.applied)
            all_reviewed.extend(result.reviewed)
            all_rejected.extend(result.rejected)
            seen.append(workflow)

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
            "rounds": rounds,
            "operations": [vars(x) for x in all_operations],
            "applied": all_applied,
            "reviewed": all_reviewed,
            "rejected": all_rejected,
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
