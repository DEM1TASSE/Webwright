#!/usr/bin/env python3
"""Export approved adapter reviews to the audited builder's source-manifest contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def export(review_paths: list[str | Path], output: str | Path) -> dict:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    sources = []
    for review_path in review_paths:
        review = load_json(review_path)
        task_id = str(review["task_id"])
        admitted = [row for row in review.get("segments", []) if row.get("admitted") is True]
        if not admitted:
            continue
        segment_path = root / f"{task_id}.segments.json"
        segment_path.write_text(json.dumps({task_id: [{
            "segment_id": row["segment_id"], "site": row["site"],
            "goal": row["goal"], "template_id": row["template_id"],
            "rubric_ids": row["rubric_ids"], "required_fields": row["required_fields"],
        } for row in admitted]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sources.append({
            "task_id": task_id, "mode": "scratch", "run_dir": review["run_dir"],
            "segments": str(segment_path),
            "segment_code": {row["segment_id"]: row["code_path"] for row in admitted},
        })
    payload = {"sources": sources}
    manifest = root / "source_manifest.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return {"manifest": str(manifest), "source_tasks": len(sources),
            "site_segments": sum(len(load_json(row["segments"])[row["task_id"]])
                                 for row in sources)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("reviews", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = export(args.reviews, args.output)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
