#!/usr/bin/env python3
"""Merge preliminary WebVoyager annotations and make a human-review CSV."""
from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PARTS = (ROOT / "part_a.jsonl", ROOT / "part_b.jsonl")
JSON_FIELDS = {"capabilities", "slots", "interaction_type"}


def load(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    rows = [row for part in PARTS for row in load(part)]
    ids = [row["id"] for row in rows]
    if len(ids) != 643 or len(set(ids)) != 643:
        raise SystemExit(f"expected 643 unique tasks, got {len(ids)} rows/{len(set(ids))} IDs")
    rows.sort(key=lambda row: (row["web_name"], int(row["id"].rsplit("--", 1)[-1])))
    for row in rows:
        row["annotation_version"] = "preliminary-v1"
        row["review_status"] = "pending"

    output = ROOT / "webvoyager_annotations.preliminary.jsonl"
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    fields = [
        "review_status", "id", "web_name", "ques", "task_family", "template",
        "capabilities", "slots", "interaction_type", "answer_type",
        "requires_login", "live_web_risk", "confidence", "notes",
    ]
    with (ROOT / "webvoyager_annotations.review.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            rendered = dict(row)
            for field in JSON_FIELDS:
                rendered[field] = json.dumps(rendered[field], ensure_ascii=False)
            writer.writerow(rendered)

    summary = {
        "tasks": len(rows),
        "sites": len({row["web_name"] for row in rows}),
        "families": len({(row["web_name"], row["task_family"]) for row in rows}),
        "templates": len({(row["web_name"], row["template"]) for row in rows}),
        "low_confidence_below_0_8": sum(float(row["confidence"]) < 0.8 for row in rows),
        "requires_login": sum(bool(row["requires_login"]) for row in rows),
    }
    (ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
