#!/usr/bin/env python3
"""Replay a deterministic contract guard over frozen primitive-routing decisions.

This does not call an LLM or execute a browser. It answers the narrow question: given the
primitive IDs selected in a prior run, would the current deterministic guard still expose them?
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from cross_task_eval import deterministic_direct_contract_guard


def load_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def replay(cases_path: str | Path, results_root: str | Path, library: str | Path) -> dict:
    manifest = load_json(cases_path)
    results_root = Path(results_root)
    library = Path(library)
    indexes = {}
    rows = []
    for case in manifest["cases"]:
        task_id = int(case["task_id"])
        matches = list(results_root.rglob(f"task{task_id}_primitive.json"))
        if len(matches) != 1:
            raise ValueError(f"expected one primitive result for task {task_id}, got {matches}")
        previous = load_json(matches[0])
        site = previous["site"]
        if site not in indexes:
            index = load_json(library / site / "final_candidate" / "index.json")
            indexes[site] = {item["primitive_id"]: item for item in index["primitives"]}
        selected_ids = [item["primitive_id"] for item in previous["retrieved_primitives"]]
        selected = [indexes[site][primitive_id] for primitive_id in selected_ids]
        reason = deterministic_direct_contract_guard(
            previous["task_intent"], selected, site=site,
        )
        old_decision = previous["route_decision"]
        new_decision = "skip" if reason else old_decision
        rows.append({
            **case,
            "site": site,
            "task_intent": previous["task_intent"],
            "selected_primitive_ids": selected_ids,
            "old_decision": old_decision,
            "new_decision": new_decision,
            "guard_reason": reason,
        })
    transitions = Counter(f"{row['old_decision']}->{row['new_decision']}" for row in rows)
    return {
        "kind": "deterministic_guard_replay",
        "source_cases": str(cases_path),
        "source_results": str(results_root),
        "library": str(library),
        "case_count": len(rows),
        "transitions": dict(sorted(transitions.items())),
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = replay(args.cases, args.results, args.library)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("case_count", "transitions")}, indent=2))


if __name__ == "__main__":
    main()
