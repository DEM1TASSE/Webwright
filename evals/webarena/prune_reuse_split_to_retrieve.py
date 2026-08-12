#!/usr/bin/env python3
"""Correct a legacy split whose evaluator-only filter admitted mutation tasks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sample_reuse_split import is_retrieve_only, summarise, validate  # noqa: E402


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prune(split, tasks):
    by_id = {task["task_id"]: task for task in tasks}
    corrected = json.loads(json.dumps(split))
    removed_train = []
    for site, rows in corrected["train"].items():
        kept = []
        for row in rows:
            invalid_t1 = [task_id for task_id in row.get("t1_heldout_task_ids", [])
                          if not is_retrieve_only(by_id[task_id])]
            if invalid_t1:
                raise ValueError(f"T1 contains non-retrieve tasks {invalid_t1}; rebuild required")
            valid_build = [task_id for task_id in row["build_task_ids"]
                           if is_retrieve_only(by_id[task_id])]
            removed_train.extend(task_id for task_id in row["build_task_ids"]
                                 if task_id not in valid_build)
            if valid_build:
                row["build_task_ids"] = valid_build
                kept.append(row)
        corrected["train"][site] = kept

    removed_t2 = []
    for site, rows in corrected["test"].items():
        kept = []
        for row in rows:
            valid = [task_id for task_id in row["t2_task_ids"]
                     if is_retrieve_only(by_id[task_id])]
            removed_t2.extend(task_id for task_id in row["t2_task_ids"] if task_id not in valid)
            if valid:
                row["t2_task_ids"] = valid
                kept.append(row)
        corrected["test"][site] = kept
    corrected["design"]["retrieve_only_correction"] = (
        "Before formal browser evaluation, remove TRAIN/T2 tasks whose expected task_type is not "
        "retrieve or whose intent begins with a state-changing action verb. The original TRAIN "
        "solve remains in the raw attempt log but is ineligible for library construction."
    )
    corrected["design"]["retrieve_only_removed_train_task_ids"] = removed_train
    corrected["design"]["retrieve_only_removed_t2_task_ids"] = removed_t2
    return corrected, removed_train, removed_t2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--md", required=True)
    args = ap.parse_args()
    tasks = load(args.dataset)
    corrected, removed_train, removed_t2 = prune(load(args.split), tasks)
    errors = validate(corrected, tasks)
    if errors:
        raise SystemExit("\n".join(errors))
    Path(args.split).write_text(json.dumps(corrected, ensure_ascii=False, indent=1) + "\n")
    Path(args.md).write_text(summarise(corrected) + "\n")
    print(json.dumps({"removed_train_task_ids": removed_train,
                      "removed_t2_task_ids": removed_t2, "remaining_train": sum(
        len(row["build_task_ids"]) for rows in corrected["train"].values() for row in rows
    ), "remaining_t2": sum(
        len(row["t2_task_ids"]) for rows in corrected["test"].values() for row in rows
    )}))


if __name__ == "__main__":
    main()
