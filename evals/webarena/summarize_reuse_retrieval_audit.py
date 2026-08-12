#!/usr/bin/env python3
"""Validate completeness/isolation of per-site retrieval audits and write a summary."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def expected_keys(split):
    keys = set()
    for site, rows in split["train"].items():
        for row in rows:
            keys.update(("t1", "workflow", site, task_id)
                        for task_id in row.get("t1_heldout_task_ids", []))
    for site, rows in split["test"].items():
        for row in rows:
            for task_id in row["t2_task_ids"]:
                keys.add(("t2", "workflow", site, task_id))
                keys.add(("t2", "primitive", site, task_id))
    return keys


def summarize(split, audit_dir):
    rows = []
    for path in sorted(Path(audit_dir).glob("*.json")):
        if path.name != "summary.json":
            rows.extend(load(path))
    actual = [(row["partition"], row["arm"], row["site"], row["task_id"])
              for row in rows]
    expected = expected_keys(split)
    duplicates = sorted(key for key, count in Counter(actual).items() if count > 1)
    missing = sorted(expected - set(actual))
    unexpected = sorted(set(actual) - expected)
    errors = [row for row in rows if row.get("decision") == "error"]
    invalid = [row for row in rows if row.get("decision") not in {"use", "adapt", "skip"}]
    counts = Counter((row["partition"], row["arm"], row["decision"]) for row in rows)
    return {
        "valid": not (duplicates or missing or unexpected or errors or invalid),
        "records": len(rows),
        "expected_records": len(expected),
        "counts": {"/".join(key): value for key, value in sorted(counts.items())},
        "duplicates": duplicates,
        "missing": missing,
        "unexpected": unexpected,
        "errors": errors,
        "invalid_decisions": invalid,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", required=True)
    parser.add_argument("--audit-dir", required=True)
    args = parser.parse_args()
    result = summarize(load(args.split), args.audit_dir)
    output = Path(args.audit_dir) / "summary.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(not result["valid"])


if __name__ == "__main__":
    raise SystemExit(main())
