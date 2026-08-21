#!/usr/bin/env python3
"""Adapt an Official WebArena ID split and full812 results to the V12 reuse pipeline."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load(path: Path | str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def result_path(roots: list[Path], site: str, task_id: int) -> Path:
    matches = [root / site / f"task{task_id}.json" for root in roots]
    matches = [path for path in matches if path.is_file()]
    if len(matches) != 1:
        raise ValueError(f"task {task_id}: expected one result, found {matches}")
    return matches[0]


def normalize_result(source: dict, task: dict, source_path: Path) -> dict:
    run = source.get("run") or {}
    evaluation = source.get("evaluation") or {}
    score = evaluation.get("score")
    status = evaluation.get("status")
    run_dir = Path(run.get("run_dir") or "")
    correct = score == 1.0 and status == "scored_correct"
    has_final_script = (run_dir / "final_script.py").is_file()
    if correct and not has_final_script:
        raise ValueError(f"{source_path}: missing trajectory final_script.py under {run_dir}")
    final_state_path = run_dir / "final_state.json"
    final_state = load(final_state_path) if final_state_path.is_file() else {}
    answer = final_state.get("answer")
    return {
        "task_id": task["task_id"],
        "site": task["sites"][0],
        "intent_template_id": task["intent_template_id"],
        "task_intent": task["intent"],
        "task_type": None,
        "score": score,
        "correct": correct,
        "run_status": status,
        "timed_out": bool(run.get("timed_out")),
        "run_dir": str(run_dir.resolve()),
        "has_final_script": has_final_script,
        "answer": answer,
        "retrieved_primitives": [],
        "source_result": str(source_path.resolve()),
        "evaluation": evaluation,
        "deployment": source.get("deployment"),
    }


def adapt(split: dict, dataset: list[dict], result_roots: list[Path], output: Path,
          *, split_path: Path, dataset_path: Path) -> dict:
    tasks = {row["task_id"]: row for row in dataset}
    train_ids, test_ids = split["train"], split["test"]
    if set(train_ids) & set(test_ids):
        raise ValueError("train and test overlap")
    missing = (set(train_ids) | set(test_ids)) - set(tasks)
    if missing:
        raise ValueError(f"split IDs missing from dataset: {sorted(missing)}")

    partition_rows = {"train": defaultdict(lambda: defaultdict(list)),
                      "test": defaultdict(lambda: defaultdict(list))}
    admitted = defaultdict(list)
    normalized_root = output / "normalized_results"
    correct = {"train": 0, "test": 0}

    for partition, ids in (("train", train_ids), ("test", test_ids)):
        for task_id in ids:
            task = tasks[task_id]
            site = task["sites"][0]
            template_id = task["intent_template_id"]
            meta = split["template_meta"][str(template_id)]
            source_path = result_path(result_roots, site, task_id)
            record = normalize_result(load(source_path), task, source_path)
            record["task_type"] = meta["type"]
            destination = normalized_root / site / f"task{task_id}_scratch.json"
            write(destination, record)
            partition_rows[partition][site][template_id].append(task_id)
            if record["correct"]:
                correct[partition] += 1
                if partition == "train":
                    admitted[site].append(str(destination.resolve()))

    reuse_split = {"tier": split.get("tier"), "task_type": "retrieve", "train": {}, "test": {}}
    for partition in ("train", "test"):
        key = "build_task_ids" if partition == "train" else "t2_task_ids"
        for site, templates in sorted(partition_rows[partition].items()):
            reuse_split[partition][site] = [
                {"intent_template_id": template_id,
                 "task_type": split["template_meta"][str(template_id)]["type"],
                 key: sorted(ids)}
                for template_id, ids in sorted(templates.items())
            ]

    if split.get("tier") == "same_template":
        # T1 runner reads held-out IDs from the corresponding TRAIN template row.
        heldout = {
            (site, row["intent_template_id"]): row["t2_task_ids"]
            for site, rows in reuse_split["test"].items() for row in rows
        }
        for site, rows in reuse_split["train"].items():
            for row in rows:
                row["workflow_skill"] = True
                row["t1_heldout_task_ids"] = heldout.get(
                    (site, row["intent_template_id"]), []
                )

    manifest = {"schema_version": 1, "source_split": str(split_path.resolve()),
                "dataset": str(dataset_path.resolve()),
                "results_roots": [str(path.resolve()) for path in result_roots],
                "counts": {"train": len(train_ids), "test": len(test_ids),
                           "train_gold_admitted": correct["train"],
                           "test_baseline_correct": correct["test"]},
                "paths": {"reuse_split": "reuse_split.json",
                          "build_manifest": "by_site.json",
                          "normalized_results": "normalized_results"}}
    write(output / "reuse_split.json", reuse_split)
    write(output / "by_site.json", dict(sorted(admitted.items())))
    write(output / "train_ids.json", train_ids)
    write(output / "test_ids.json", test_ids)
    write(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--nonmutate-results", required=True)
    parser.add_argument("--mutate-results", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    split_path, dataset_path = Path(args.split), Path(args.dataset)
    split = load(split_path)
    if "template_meta" not in split:
        metadata_split = split_path.with_name("cross_template.json")
        metadata = load(metadata_split)
        if "template_meta" not in metadata:
            raise ValueError(f"task-type metadata missing from {metadata_split}")
        split["template_meta"] = metadata["template_meta"]
    result = adapt(split, load(dataset_path),
                   [Path(args.nonmutate_results), Path(args.mutate_results)], Path(args.output),
                   split_path=split_path, dataset_path=dataset_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
