#!/usr/bin/env python3
"""Merge preliminary WebVoyager annotations and make a human-review CSV."""
from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PARTS = (ROOT / "part_a.jsonl", ROOT / "part_b.jsonl")
REVIEWS = (ROOT / "review_a.jsonl", ROOT / "review_b.jsonl", ROOT / "review_c.jsonl")
STRICT_REVIEWS = (
    ROOT / "review_strict_a.jsonl",
    ROOT / "review_strict_b.jsonl",
    ROOT / "review_strict_c.jsonl",
)
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

    reviews = {row["id"]: row for path in REVIEWS for row in load(path)}
    if set(reviews) != set(ids):
        raise SystemExit("second-pass reviews do not exactly cover official task IDs")
    reviewed_rows = []
    for row in rows:
        review = reviews[row["id"]]
        revised = dict(row)
        revised["template_v1"] = row["template"]
        revised["template"] = review["reviewed_template"]
        revised["template_review_decision"] = review["decision"]
        revised["template_review_confidence"] = review["confidence"]
        revised["template_review_rationale"] = review["rationale"]
        revised["annotation_version"] = "template-review-v2"
        reviewed_rows.append(revised)

    reviewed_output = ROOT / "webvoyager_annotations.reviewed_v2.jsonl"
    reviewed_output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in reviewed_rows),
        encoding="utf-8",
    )
    review_fields = [
        "review_status", "id", "web_name", "ques", "template_v1", "template",
        "template_review_decision", "template_review_confidence",
        "template_review_rationale", "capabilities", "slots", "live_web_risk",
    ]
    with (ROOT / "webvoyager_annotations.reviewed_v2.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields, extrasaction="ignore")
        writer.writeheader()
        for row in reviewed_rows:
            rendered = dict(row)
            for field in ("capabilities", "slots"):
                rendered[field] = json.dumps(rendered[field], ensure_ascii=False)
            writer.writerow(rendered)

    summary["reviewed_templates"] = len(
        {(row["web_name"], row["template"]) for row in reviewed_rows}
    )
    summary["template_changes"] = sum(
        row["template_review_decision"] == "change" for row in reviewed_rows
    )
    (ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "reviewed_templates": summary["reviewed_templates"],
        "template_changes": summary["template_changes"],
    }, ensure_ascii=False, indent=2))

    strict_reviews = {row["id"]: row for path in STRICT_REVIEWS for row in load(path)}
    if set(strict_reviews) != set(ids):
        raise SystemExit("strict reviews do not exactly cover official task IDs")
    strict_rows = []
    for row in reviewed_rows:
        review = strict_reviews[row["id"]]
        revised = dict(row)
        revised["template_v2"] = row["template"]
        revised["template"] = review["strict_template"]
        revised["strict_review_decision"] = review["decision"]
        revised["strict_review_confidence"] = review["confidence"]
        revised["strict_review_rationale"] = review["rationale"]
        revised["annotation_version"] = "webarena-granularity-v3"
        strict_rows.append(revised)

    (ROOT / "webvoyager_annotations.strict_v3.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in strict_rows),
        encoding="utf-8",
    )
    strict_fields = [
        "review_status", "id", "web_name", "ques", "template_v2", "template",
        "strict_review_decision", "strict_review_confidence",
        "strict_review_rationale", "capabilities", "slots", "live_web_risk",
    ]
    with (ROOT / "webvoyager_annotations.strict_v3.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=strict_fields, extrasaction="ignore")
        writer.writeheader()
        for row in strict_rows:
            rendered = dict(row)
            for field in ("capabilities", "slots"):
                rendered[field] = json.dumps(rendered[field], ensure_ascii=False)
            writer.writerow(rendered)

    summary["strict_templates"] = len(
        {(row["web_name"], row["template"]) for row in strict_rows}
    )
    summary["strict_changes_from_v2"] = sum(
        row["strict_review_decision"] == "change" for row in strict_rows
    )
    (ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "strict_templates": summary["strict_templates"],
        "strict_changes_from_v2": summary["strict_changes_from_v2"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
