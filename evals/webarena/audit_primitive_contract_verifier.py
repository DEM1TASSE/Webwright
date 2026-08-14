#!/usr/bin/env python3
"""Replay frozen primitive proposals through the contract verifier only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cross_task_eval import (  # noqa: E402
    configure_router_model,
    verify_direct_primitive_contract,
)
from webwright.skill_factory.audited_primitive_retrieve import load_candidate_index  # noqa: E402


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validated_verdict(raw):
    checks = raw.get("checks") or {}
    required = {"input_reachability", "guarantee_sufficiency", "closed_acquisition"}
    accepted = (
        raw.get("verdict") == "accept"
        and set(checks) == required
        and all(value == "pass" for value in checks.values())
        and bool(raw.get("closed_acquisitions"))
    )
    return "accept" if accepted else "reject"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--frozen-results", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument("--task-ids", nargs="+", type=int, required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    tasks = {row["task_id"]: row for row in load(args.dataset)}
    configure_router_model(args.model_config)
    result_root = Path(args.frozen_results)
    indexes = {}
    rows = []
    for task_id in args.task_ids:
        matches = list(result_root.glob(f"*/task{task_id}_primitive.json"))
        if len(matches) != 1:
            raise ValueError(f"task {task_id}: expected one frozen result, got {matches}")
        frozen = load(matches[0])
        site = frozen["site"]
        if site not in indexes:
            index = load_candidate_index(args.library, site)
            indexes[site] = {row["primitive_id"]: row for row in index["primitives"]}
        proposal = {
            "decision": frozen.get("route_decision"),
            "primitive_ids": [row["primitive_id"] for row in frozen.get("retrieved_primitives", [])],
            "reason": frozen.get("route_reason"),
            "remaining_gap": frozen.get("route_remaining_gap") or [],
        }
        selected = [indexes[site][pid] for pid in proposal["primitive_ids"]]
        if proposal["decision"] == "skip" or not selected:
            row = {"task_id": task_id, "site": site, "original_decision": "skip",
                   "verifier_decision": "not_applicable"}
        else:
            raw = verify_direct_primitive_contract(tasks[task_id]["intent"], proposal, selected)
            row = {"task_id": task_id, "site": site,
                   "original_decision": proposal["decision"],
                   "primitive_ids": proposal["primitive_ids"],
                   "verifier_decision": validated_verdict(raw), "verifier": raw}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
