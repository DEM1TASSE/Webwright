#!/usr/bin/env python3
"""Build the frozen template-disjoint Retrieve+Navigate primitive split."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


SITES = ("gitlab", "shopping", "shopping_admin", "reddit", "map")
TASK_TYPES = ("retrieve", "navigate")
TRAIN_QUOTAS = {
    "gitlab": {"retrieve": 8, "navigate": 2},
    "shopping": {"retrieve": 11, "navigate": 7},
    "shopping_admin": {"retrieve": 10, "navigate": 2},
    "reddit": {"retrieve": 2, "navigate": 0},
    "map": {"retrieve": 11, "navigate": 3},
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stable_key(seed, *parts):
    payload = "\0".join([seed, *(str(part) for part in parts)])
    return hashlib.sha256(payload.encode()).hexdigest()


def verified_task_type(row):
    evaluators = row.get("eval") or []
    expected = evaluators[0].get("expected", {}) if evaluators else {}
    task_type = str(expected.get("task_type", "")).lower()
    return task_type if task_type in TASK_TYPES else None


def validate_official(verified, official):
    by_id = {row["task_id"]: row for row in official}
    if len(by_id) != len(official):
        raise ValueError("official dataset has duplicate task IDs")
    for row in verified:
        task_id = row["task_id"]
        if task_id not in by_id:
            raise ValueError(f"verified task {task_id} is missing from official dataset")
        other = by_id[task_id]
        if row.get("intent_template_id") != other.get("intent_template_id"):
            raise ValueError(f"task {task_id}: intent_template_id differs across datasets")
        if row.get("sites") != other.get("sites"):
            raise ValueError(f"task {task_id}: sites differ across datasets")


def build_split(verified, official, seed="primitive-rt-v1"):
    validate_official(verified, official)
    groups = defaultdict(list)
    for row in verified:
        sites = row.get("sites") or []
        task_type = verified_task_type(row)
        if len(sites) != 1 or sites[0] not in SITES or task_type not in TASK_TYPES:
            continue
        key = (sites[0], task_type, row["intent_template_id"])
        groups[key].append(row["task_id"])

    train = {site: [] for site in SITES}
    test = {site: [] for site in SITES}
    for site in SITES:
        for task_type in TASK_TYPES:
            candidates = [
                (template_id, sorted(task_ids))
                for (candidate_site, candidate_type, template_id), task_ids in groups.items()
                if candidate_site == site and candidate_type == task_type
            ]
            eligible = [(template_id, ids) for template_id, ids in candidates if len(ids) >= 3]
            eligible.sort(key=lambda item: stable_key(seed, site, task_type, item[0]))
            quota = TRAIN_QUOTAS[site][task_type]
            if len(eligible) < quota:
                raise ValueError(
                    f"{site}/{task_type}: need {quota} templates with >=3 tasks, found {len(eligible)}"
                )
            selected = {template_id for template_id, _ in eligible[:quota]}
            for template_id, task_ids in sorted(candidates):
                shuffled = sorted(
                    task_ids, key=lambda task_id: stable_key(seed, site, task_type, template_id, task_id)
                )
                common = {
                    "intent_template_id": template_id,
                    "task_type": task_type,
                    "n_instances": len(task_ids),
                }
                if template_id in selected:
                    train[site].append({
                        **common,
                        "build_task_ids": shuffled[:3],
                        "unused_task_ids": shuffled[3:],
                    })
                else:
                    test[site].append({
                        **common,
                        "t2_task_ids": sorted(task_ids),
                        "long_tail": len(task_ids) < 3,
                    })

    split = {
        "schema_version": 2,
        "split_id": "primitive_rt_template_disjoint_v1",
        "seed": seed,
        "sites": list(SITES),
        "task_types": list(TASK_TYPES),
        "protocol": {
            "train_selection": "deterministic hash ordering within fixed site/type quotas",
            "source_instances_per_template": 3,
            "test_selection": "all instances from templates absent from train",
            "runtime_tasks_and_evaluator": "official WebArena",
            "task_type_and_template_metadata": "WebArena Verified",
        },
        "train": train,
        "test": test,
    }
    split["summary"] = validate_split(split)
    return split


def validate_split(split):
    train_templates = set()
    test_templates = set()
    train_tasks = set()
    test_tasks = set()
    per_site = {}
    for site in SITES:
        train_rows = split["train"][site]
        test_rows = split["test"][site]
        for row in train_rows:
            key = (site, row["task_type"], row["intent_template_id"])
            train_templates.add(key)
            if len(row["build_task_ids"]) != 3:
                raise ValueError(f"{key}: TRAIN must use exactly three source instances")
            train_tasks.update(row["build_task_ids"])
        for row in test_rows:
            key = (site, row["task_type"], row["intent_template_id"])
            test_templates.add(key)
            test_tasks.update(row["t2_task_ids"])
        per_site[site] = {
            "train_templates": len(train_rows),
            "train_tasks": sum(len(row["build_task_ids"]) for row in train_rows),
            "test_templates": len(test_rows),
            "test_tasks": sum(len(row["t2_task_ids"]) for row in test_rows),
            "test_long_tail_templates": sum(bool(row["long_tail"]) for row in test_rows),
        }
    overlap_templates = train_templates & test_templates
    overlap_tasks = train_tasks & test_tasks
    if overlap_templates or overlap_tasks:
        raise ValueError(f"split leakage: templates={overlap_templates}, tasks={overlap_tasks}")
    summary = {
        "train_templates": len(train_templates),
        "train_tasks": len(train_tasks),
        "test_templates": len(test_templates),
        "test_tasks": len(test_tasks),
        "test_long_tail_templates": sum(
            bool(row["long_tail"]) for rows in split["test"].values() for row in rows
        ),
        "by_site": per_site,
    }
    if summary["train_templates"] != 56 or summary["train_tasks"] != 168:
        raise ValueError(f"unexpected TRAIN size: {summary}")
    if summary["test_templates"] != 57:
        raise ValueError(f"unexpected TEST template count: {summary}")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verified-dataset", required=True)
    ap.add_argument("--official-dataset", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--seed", default="primitive-rt-v1")
    args = ap.parse_args()
    split = build_split(load(args.verified_dataset), load(args.official_dataset), args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(split, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(split["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
