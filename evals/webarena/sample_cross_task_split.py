#!/usr/bin/env python3
"""Create a reproducible template-disjoint, retrieve-only WebArena split."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


DEFAULT_SITES = ("shopping", "gitlab", "shopping_admin", "map")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def seeded_key(seed, site, kind, value):
    payload = f"{seed}\0{site}\0{kind}\0{value}".encode()
    return hashlib.sha256(payload).hexdigest()


def eligible_tasks(dataset, site):
    """Return pure retrieve tasks supported by the current response evaluator."""
    rows = []
    for task in dataset:
        evaluators = task.get("eval") or []
        if task.get("sites") != [site] or len(evaluators) != 1:
            continue
        evaluator = evaluators[0]
        expected = evaluator.get("expected") or {}
        if evaluator.get("evaluator") != "AgentResponseEvaluator":
            continue
        if str(expected.get("task_type", "")).lower() != "retrieve":
            continue
        if "intent_template_id" not in task or "task_id" not in task:
            continue
        rows.append(task)
    return rows


def sample_site(dataset, site, seed, train_templates, test_templates):
    by_template = defaultdict(list)
    for task in eligible_tasks(dataset, site):
        by_template[task["intent_template_id"]].append(task["task_id"])
    needed = train_templates + test_templates
    if len(by_template) < needed:
        raise ValueError(f"{site}: need {needed} templates, found {len(by_template)}")
    templates = sorted(
        by_template,
        key=lambda tid: seeded_key(seed, site, "template", tid),
    )[:needed]
    train_ids = templates[:train_templates]
    test_ids = templates[train_templates:]

    def pick(template_id):
        return min(
            by_template[template_id],
            key=lambda task_id: seeded_key(seed, site, f"instance:{template_id}", task_id),
        )

    return {
        "site": site,
        "seed": seed,
        "eligibility": {
            "single_site": True,
            "task_type": "retrieve",
            "evaluators": ["AgentResponseEvaluator"],
        },
        "eligible_template_count": len(by_template),
        "source": {
            "intent_template_ids": train_ids,
            "task_ids": [pick(tid) for tid in train_ids],
        },
        "heldout": [
            {"intent_template_id": tid, "task_ids": [pick(tid)]}
            for tid in test_ids
        ],
    }


def create_split(dataset, output, seed, sites, train_templates, test_templates):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    site_files = {}
    for site in sites:
        split = sample_site(dataset, site, seed, train_templates, test_templates)
        filename = f"{site}.json"
        (output / filename).write_text(
            json.dumps(split, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        site_files[site] = filename
    manifest = {
        "protocol": "seeded template-random cross-template retrieve-only train/test",
        "seed": seed,
        "sites": site_files,
        "train": {
            "templates_per_site": train_templates,
            "instances_per_template": 1,
            "total_tasks": len(sites) * train_templates,
        },
        "test": {
            "templates_per_site": test_templates,
            "instances_per_template": 1,
            "total_tasks": len(sites) * test_templates,
            "paired_arms": ["scratch", "routed"],
            "total_runs": len(sites) * test_templates * 2,
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--sites", nargs="+", default=list(DEFAULT_SITES))
    parser.add_argument("--train-templates", type=int, default=8)
    parser.add_argument("--test-templates", type=int, default=6)
    args = parser.parse_args()
    manifest = create_split(
        load(args.dataset), args.output, args.seed, args.sites,
        args.train_templates, args.test_templates,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
