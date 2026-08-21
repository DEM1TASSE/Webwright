#!/usr/bin/env python3
"""Pair frozen reuse-arm results with the existing 812-task official scratch baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def ids(path: str) -> list[int]:
    return [int(value) for value in load(Path(path))]


def exact_mcnemar(wins: int, losses: int) -> float | None:
    n = wins + losses
    if not n:
        return None
    tail = sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / (2 ** n)
    return round(min(1.0, 2 * tail), 8)


def baseline_index(roots: list[str]) -> dict[int, dict]:
    out = {}
    for value in roots:
        for path in Path(value).rglob("task*.json"):
            record = load(path)
            task_id = int((record.get("run") or {}).get("task_id", -1))
            if task_id < 0:
                continue
            if task_id in out:
                raise ValueError(f"duplicate baseline task {task_id}: {path}")
            out[task_id] = record
    return out


def treatment_index(root: Path, partition: str, arm: str) -> dict[int, dict]:
    out = {}
    for path in (root / partition / arm).glob(f"*/task*_{arm}.json"):
        record = load(path)
        task_id = int(record["task_id"])
        if task_id in out:
            raise ValueError(f"duplicate treatment task {task_id}: {path}")
        record["_path"] = str(path)
        out[task_id] = record
    return out


def summarize_arm(expected: list[int], baseline: dict[int, dict], treatment: dict[int, dict]) -> dict:
    missing_baseline = sorted(set(expected) - baseline.keys())
    missing_treatment = sorted(set(expected) - treatment.keys())
    pairs = []
    outcomes = Counter()
    for task_id in expected:
        if task_id not in baseline or task_id not in treatment:
            continue
        base_score = (baseline[task_id].get("evaluation") or {}).get("score")
        base = base_score == 1.0
        treated = treatment[task_id].get("correct") is True
        outcome = ("win" if treated and not base else "loss" if base and not treated
                   else "both_correct" if base else "both_wrong")
        outcomes[outcome] += 1
        pairs.append({
            "task_id": task_id, "site": treatment[task_id].get("site"),
            "intent_template_id": treatment[task_id].get("intent_template_id"),
            "scratch": base, "treatment": treated, "outcome": outcome,
            "route_decision": treatment[task_id].get("route_decision"),
        })
    wins, losses = outcomes["win"], outcomes["loss"]
    return {
        "expected": len(expected), "pairs": len(pairs),
        "missing_baseline": missing_baseline, "missing_treatment": missing_treatment,
        "scratch_correct": sum(row["scratch"] for row in pairs),
        "treatment_correct": sum(row["treatment"] for row in pairs),
        "scratch_accuracy": round(sum(row["scratch"] for row in pairs) / len(pairs), 4) if pairs else None,
        "treatment_accuracy": round(sum(row["treatment"] for row in pairs) / len(pairs), 4) if pairs else None,
        "wins": wins, "losses": losses, "both_correct": outcomes["both_correct"],
        "both_wrong": outcomes["both_wrong"], "net_wins": wins - losses,
        "mcnemar_exact_two_sided_p": exact_mcnemar(wins, losses),
        "route_decisions": dict(Counter(
            treatment[row["task_id"]].get("route_decision") or "none" for row in pairs
        )),
        "pairs_detail": pairs,
    }


def replay_summary(root: Path, partition: str, arm: str) -> dict:
    rows = [load(path) for path in (root / partition / arm).glob(f"*/task*_{arm}.json")]
    scored = [row for row in rows if (row.get("replay") or {}).get("score") is not None]
    return {
        "records": len(rows), "scored": len(scored),
        "correct": sum((row.get("replay") or {}).get("score") == 1.0 for row in scored),
        "matches_inline": sum(row.get("matches_inline") is True for row in scored),
        "mismatches_inline": [row["task_id"] for row in scored if row.get("matches_inline") is False],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--replay-results-root", required=True)
    ap.add_argument("--baseline-root", action="append", required=True)
    ap.add_argument("--t1-ids", required=True)
    ap.add_argument("--t2-ids", required=True)
    ap.add_argument("--freeze-manifest", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    results = Path(args.results_root)
    replays = Path(args.replay_results_root)
    baseline = baseline_index(args.baseline_root)
    arms = {
        "t1/workflow": summarize_arm(
            ids(args.t1_ids), baseline, treatment_index(results, "t1", "workflow")),
        "t2/primitive": summarize_arm(
            ids(args.t2_ids), baseline, treatment_index(results, "t2", "primitive")),
    }
    replay = {
        "t1/workflow": replay_summary(replays, "t1", "workflow"),
        "t2/primitive": replay_summary(replays, "t2", "primitive"),
    }
    freeze = Path(args.freeze_manifest)
    value = {
        "valid": all(not row["missing_baseline"] and not row["missing_treatment"]
                     for row in arms.values()),
        "freeze_manifest": str(freeze.resolve()),
        "freeze_manifest_sha256": hashlib.sha256(freeze.read_bytes()).hexdigest(),
        "baseline_records": len(baseline), "arms": arms, "replay": replay,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": value["valid"], "baseline_records": len(baseline),
                      "t1_pairs": arms["t1/workflow"]["pairs"],
                      "t2_pairs": arms["t2/primitive"]["pairs"]}))
    return int(not value["valid"])


if __name__ == "__main__":
    raise SystemExit(main())
