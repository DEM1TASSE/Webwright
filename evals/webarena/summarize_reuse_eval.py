#!/usr/bin/env python3
"""Summarize paired reuse_split_v1 evaluation records."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def expected(split, partition):
    section = split["train"] if partition == "t1" else split["test"]
    key = "t1_heldout_task_ids" if partition == "t1" else "t2_task_ids"
    return [(site, row["intent_template_id"], task_id)
            for site, rows in section.items() for row in rows for task_id in row.get(key, [])]


def read_records(root, partition, arm):
    return {int(row["task_id"]): row for path in (Path(root) / partition / arm).rglob("task*.json")
            if (row := load(path)).get("mode") == arm}


def arm_metrics(rows, task_ids):
    observed = [rows[task_id] for task_id in task_ids if task_id in rows]
    steps = [row.get("steps", 0) for row in observed]
    return {
        "expected": len(task_ids), "observed": len(observed),
        "correct": sum(row.get("correct") is True for row in observed),
        "incorrect": sum(row.get("correct") is False for row in observed),
        "infra_error": sum(row.get("correct") is None for row in observed),
        "timeouts": sum(bool(row.get("timed_out")) for row in observed),
        "mean_steps": sum(steps) / len(steps) if steps else None,
        "workflow_exposed": sum(bool(row.get("routed_workflow_id")) for row in observed),
        "primitive_exposed": sum(bool(row.get("retrieved_primitives")) for row in observed),
        "primitive_executed": sum(bool(row.get("primitive_execution_trace")) for row in observed),
    }


def paired(base, treatment, jobs):
    pairs = [(site, template, task, base[task], treatment[task])
             for site, template, task in jobs if task in base and task in treatment]
    wins = [row for row in pairs if row[3].get("correct") is False and row[4].get("correct") is True]
    losses = [row for row in pairs if row[3].get("correct") is True and row[4].get("correct") is False]
    both_correct = [row for row in pairs if row[3].get("correct") is True and row[4].get("correct") is True]
    by_site = defaultdict(lambda: {"pairs": 0, "wins": 0, "losses": 0})
    for row in pairs:
        site = row[0]
        by_site[site]["pairs"] += 1
        by_site[site]["wins"] += row in wins
        by_site[site]["losses"] += row in losses
    return {
        "pairs": len(pairs), "wins": len(wins), "losses": len(losses),
        "net_wins": len(wins) - len(losses), "both_correct": len(both_correct),
        "mean_step_delta_on_both_correct": (
            sum(row[4].get("steps", 0) - row[3].get("steps", 0) for row in both_correct)
            / len(both_correct) if both_correct else None
        ),
        "win_task_ids": [row[2] for row in wins], "loss_task_ids": [row[2] for row in losses],
        "by_site": dict(by_site),
    }


def summarize(split, root):
    output = {}
    for partition, arms in (("t1", ["scratch", "workflow"]),
                            ("t2", ["scratch", "workflow", "primitive"])):
        jobs = expected(split, partition)
        ids = [row[2] for row in jobs]
        records = {arm: read_records(root, partition, arm) for arm in arms}
        output[partition] = {
            "arms": {arm: arm_metrics(records[arm], ids) for arm in arms},
            "paired": {arm: paired(records["scratch"], records[arm], jobs)
                       for arm in arms if arm != "scratch"},
        }
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    result = summarize(load(args.split), args.results_root)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
