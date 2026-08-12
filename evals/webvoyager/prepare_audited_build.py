#!/usr/bin/env python3
"""Create audited-builder inputs from GPT-4o-admitted WebVoyager scratch records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--records", nargs="+", required=True)
    parser.add_argument("--dataset-output", required=True)
    parser.add_argument("--manifest-output", required=True)
    args = parser.parse_args(argv)
    annotations = {row["id"]: row for row in load_jsonl(args.annotations)}
    dataset, manifest = [], {"github_com": []}
    for record_path in args.records:
        record = json.loads(Path(record_path).read_text(encoding="utf-8"))
        if record.get("score") != 1.0 or record.get("correct") is not True:
            raise ValueError(f"source not GPT-4o-admitted: {record_path}")
        task_id = str(record["task_id"])
        annotation = annotations[task_id]
        dataset.append({
            "task_id": task_id,
            "intent_template_id": annotation["template_id"],
            "intent": annotation["ques"],
            "sites": ["github_com"],
        })
        manifest["github_com"].append(record_path)
    if len({row["intent_template_id"] for row in dataset}) < 2:
        raise ValueError("cross-template source build requires at least two templates")
    Path(args.dataset_output).write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    Path(args.manifest_output).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
