#!/usr/bin/env python3
"""Rescore completed official-WebArena artifacts after evaluator infrastructure fixes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cross_task_eval import score_navigate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--webarena-tasks", required=True)
    ap.add_argument("--webarena-root", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument(
        "--all-completed", action="store_true",
        help=("Rescore every completed artifact, not only evaluator infrastructure errors. "
              "Uses each result's recorded per-task deployment config when available."),
    )
    ap.add_argument("--task-ids", nargs="*", type=int)
    ap.add_argument(
        "--eval-types", nargs="*",
        help="Optional deterministic subset, for example url_match after URL canonicalization.",
    )
    args = ap.parse_args()
    changed = failed = 0
    for path in sorted(Path(args.results_root).glob("**/task*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        eligible = (
            record.get("run_status") in {"scored_correct", "scored_incorrect"}
            if args.all_completed else
            record.get("run_status") == "evaluator_infrastructure_error"
        )
        if not eligible:
            continue
        if args.task_ids is not None and int(record.get("task_id", -1)) not in args.task_ids:
            continue
        recorded_eval_types = set((record.get("evaluator") or {}).get("eval_types") or [])
        if args.eval_types and recorded_eval_types.isdisjoint(args.eval_types):
            continue
        run_dir = Path(record.get("run_dir") or "")
        if not (run_dir / "final_state.json").is_file():
            failed += 1
            continue
        prior = record.get("evaluator")
        prior_score = record.get("score")
        prior_run_status = record.get("run_status")
        recorded_config = Path(record.get("deployment_config") or "")
        deployment_config = recorded_config if recorded_config.is_file() else Path(args.config)
        score, evaluator = score_navigate(
            record["task_id"], run_dir, deployment_config, args.webarena_tasks,
            args.webarena_root, args.model_config,
        )
        if score is None:
            failed += 1
            continue
        record["score"] = score
        record["correct"] = score == 1.0
        record["run_status"] = "scored_correct" if score == 1.0 else "scored_incorrect"
        record["evaluator"] = evaluator
        record["evaluator_rescore"] = {
            "reason": (
                "full_rescore_after_adapter_fix"
                if args.all_completed else "retry_after_evaluator_infrastructure_fix"
            ),
            "prior": prior,
            "prior_score": prior_score,
            "prior_run_status": prior_run_status,
            "deployment_config": str(deployment_config),
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        changed += 1
        print(json.dumps({"task_id": record["task_id"], "score": score,
                          "path": str(path)}, ensure_ascii=False), flush=True)
    print(json.dumps({"rescored": changed, "remaining_failures": failed}))
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
