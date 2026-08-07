#!/usr/bin/env python3
"""Materialize gold-admitted train runs for workflow distillation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-runs", required=True)
    parser.add_argument("--golds", required=True)
    args = parser.parse_args()
    output = Path(args.output_runs)
    output.mkdir(parents=True, exist_ok=True)
    golds = {}
    for record_path in load(args.manifest):
        record = load(record_path)
        if record.get("score") != 1.0 or record.get("correct") is not True:
            raise ValueError(f"{record_path}: source is not gold-admitted")
        if record.get("retrieved_primitives"):
            raise ValueError(f"{record_path}: source consumed primitive material")
        source = Path(record["run_dir"]).resolve()
        task = load(source / "task.json")
        task_id = task["task_id"]
        answer = load(source / "agent_response.json")["retrieved_data"]
        target = output / source.name
        if target.is_symlink() and target.resolve() != source:
            target.unlink()
        if not target.exists():
            target.symlink_to(source, target_is_directory=True)
        golds[task_id] = answer
    Path(args.golds).write_text(
        json.dumps(golds, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"runs": len(golds), "golds": args.golds}))


if __name__ == "__main__":
    main()
