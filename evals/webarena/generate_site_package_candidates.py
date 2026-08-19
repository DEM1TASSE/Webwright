#!/usr/bin/env python3
"""Generate review-only site primitive packages from gold-admitted WebArena workflows."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from webwright.skill_factory.site_package_candidate import (
    generate_site_package_candidate,
    validate_site_package_candidate,
    write_candidate_bundle,
)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clean_workflow(record_path, dataset):
    record_path = Path(record_path)
    record = load(record_path)
    if record.get("score") != 1.0 or record.get("correct") is not True:
        raise ValueError(f"{record_path}: source is not gold-admitted")
    if record.get("retrieved_primitives"):
        raise ValueError(f"{record_path}: source consumed primitive material")
    task = next((row for row in dataset if row["task_id"] == record["task_id"]), None)
    if task is None:
        raise ValueError(f"{record_path}: task is missing from dataset")
    code_path = Path(record["run_dir"]) / "final_script.py"
    if not code_path.exists():
        raise ValueError(f"{record_path}: final_script.py missing")
    return {
        "id": f"task{task['task_id']}_t{task['intent_template_id']}",
        "task_id": task["task_id"],
        "template_id": task["intent_template_id"],
        "task_type": record.get("task_type", "retrieve"),
        "intent": record.get("task_intent") or task["intent"],
        "site": task["sites"][0],
        "code": code_path.read_text(encoding="utf-8"),
        "record_path": str(record_path),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    dataset = load(args.dataset)
    by_site = defaultdict(list)
    for declared_site, paths in load(args.manifest).items():
        for path in paths:
            workflow = clean_workflow(path, dataset)
            if workflow["site"] != declared_site:
                raise ValueError(f"{path}: declared site does not match dataset site")
            by_site[declared_site].append(workflow)

    summary = {"status": "candidates_only", "promoted": False, "sites": {}}
    for site, workflows in sorted(by_site.items()):
        candidate = {}
        validation = None
        attempts = []
        for attempt in range(1, max(1, args.max_attempts) + 1):
            candidate = generate_site_package_candidate(
                site,
                workflows,
                prior_candidate=candidate or None,
                validation_feedback=validation.errors if validation else None,
            )
            validation = validate_site_package_candidate(
                candidate, site=site, workflows=workflows
            )
            attempts.append({
                "attempt": attempt,
                "candidate": candidate,
                "validation": {
                    "accepted": validation.accepted,
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                },
            })
            if validation.accepted:
                break
        assert validation is not None
        path = write_candidate_bundle(
            args.output, candidate, validation, site=site, workflows=workflows
        )
        attempts_path = path / "attempts.json"
        attempts_path.write_text(
            json.dumps(attempts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        summary["sites"][site] = {
            "path": str(path),
            "static_checks": "PASS" if validation.accepted else "FAIL",
            "method_count": len(candidate.get("methods") or []),
            "attempt_count": len(attempts),
            "errors": validation.errors,
            "warnings": validation.warnings,
        }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
