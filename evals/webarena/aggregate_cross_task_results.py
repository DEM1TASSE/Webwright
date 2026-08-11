#!/usr/bin/env python3
"""Validate and aggregate the frozen multi-site train/test experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_manifest(manifest_path, dataset):
    root = Path(manifest_path).parent
    manifest = load(manifest_path)
    tasks = {x["task_id"]: x for x in dataset}
    errors = []
    train_ids, test_ids = [], []
    train_templates, test_templates = set(), set()
    for site, relative in manifest["sites"].items():
        split = load(root / relative)
        if split.get("site") != site:
            errors.append(f"{site}: split site mismatch")
            continue
        source_templates = set(split["source"]["intent_template_ids"])
        heldout_templates = {x["intent_template_id"] for x in split["heldout"]}
        source_ids = list(split["source"]["task_ids"])
        heldout_ids = [tid for group in split["heldout"] for tid in group["task_ids"]]
        if source_templates & heldout_templates:
            errors.append(f"{site}: train/test templates overlap")
        if len(source_templates) != manifest["train"]["templates_per_site"]:
            errors.append(f"{site}: wrong train template count")
        if len(heldout_templates) != manifest["test"]["templates_per_site"]:
            errors.append(f"{site}: wrong test template count")
        expected_train = (
            manifest["train"]["templates_per_site"]
            * manifest["train"]["instances_per_template"]
        )
        expected_test = (
            manifest["test"]["templates_per_site"]
            * manifest["test"]["instances_per_template"]
        )
        if len(source_ids) != expected_train:
            errors.append(f"{site}: wrong train task count")
        if len(heldout_ids) != expected_test:
            errors.append(f"{site}: wrong test task count")
        declared_source = set(source_templates)
        declared_heldout = {
            tid: group["intent_template_id"]
            for group in split["heldout"] for tid in group["task_ids"]
        }
        for task_id in source_ids:
            task = tasks.get(task_id)
            if not task:
                errors.append(f"{site}: missing train task {task_id}")
            elif task["sites"] != [site] or task["intent_template_id"] not in declared_source:
                errors.append(f"{site}: invalid train task {task_id}")
        for task_id in heldout_ids:
            task = tasks.get(task_id)
            if not task:
                errors.append(f"{site}: missing test task {task_id}")
            elif (task["sites"] != [site]
                  or task["intent_template_id"] != declared_heldout[task_id]):
                errors.append(f"{site}: invalid test task {task_id}")
        train_ids.extend(source_ids)
        test_ids.extend(heldout_ids)
        train_templates.update((site, x) for x in source_templates)
        test_templates.update((site, x) for x in heldout_templates)
    if len(train_ids) != manifest["train"]["total_tasks"]:
        errors.append("global train task count mismatch")
    if len(test_ids) != manifest["test"]["total_tasks"]:
        errors.append("global test task count mismatch")
    if set(train_ids) & set(test_ids):
        errors.append("train/test task IDs overlap")
    if train_templates & test_templates:
        errors.append("train/test site-template pairs overlap")
    return errors


def aggregate(manifest_path, results_root):
    manifest_path = Path(manifest_path)
    manifest = load(manifest_path)
    rows = {}
    totals = {
        "pairs": 0, "scratch_correct": 0, "routed_correct": 0,
        "wins": 0, "losses": 0, "ties_both_correct": 0, "ties_both_wrong": 0,
        "scratch_steps": 0, "routed_steps": 0,
    }
    decisions = {}
    by_route = {}
    for site in manifest["sites"]:
        site_dir = Path(results_root) / site
        records = {p.stem: load(p) for p in site_dir.glob("task*_*.json")}
        split = load(manifest_path.parent / manifest["sites"][site])
        task_ids = [tid for group in split["heldout"] for tid in group["task_ids"]]
        row = dict(totals)
        row.update({key: 0 for key in totals})
        for task_id in task_ids:
            scratch = records.get(f"task{task_id}_scratch")
            routed = records.get(f"task{task_id}_routed")
            if not scratch or not routed:
                continue
            if scratch.get("correct") is None or routed.get("correct") is None:
                continue
            s, r = bool(scratch["correct"]), bool(routed["correct"])
            row["pairs"] += 1
            row["scratch_correct"] += int(s)
            row["routed_correct"] += int(r)
            row["wins"] += int(r and not s)
            row["losses"] += int(s and not r)
            row["ties_both_correct"] += int(s and r)
            row["ties_both_wrong"] += int(not s and not r)
            row["scratch_steps"] += int(scratch.get("steps") or 0)
            row["routed_steps"] += int(routed.get("steps") or 0)
            decision = routed.get("route_decision") or "unrecorded"
            decisions[decision] = decisions.get(decision, 0) + 1
            route_key = f"{routed.get('route_stage') or 'none'}:{decision}"
            bucket = by_route.setdefault(route_key, {
                "pairs": 0, "scratch_correct": 0, "routed_correct": 0,
                "wins": 0, "losses": 0, "ties_both_correct": 0,
                "ties_both_wrong": 0, "scratch_steps": 0, "routed_steps": 0,
            })
            bucket["pairs"] += 1
            bucket["scratch_correct"] += int(s)
            bucket["routed_correct"] += int(r)
            bucket["wins"] += int(r and not s)
            bucket["losses"] += int(s and not r)
            bucket["ties_both_correct"] += int(s and r)
            bucket["ties_both_wrong"] += int(not s and not r)
            bucket["scratch_steps"] += int(scratch.get("steps") or 0)
            bucket["routed_steps"] += int(routed.get("steps") or 0)
        rows[site] = row
        for key in totals:
            totals[key] += row[key]
    pairs = totals["pairs"]
    return {
        "complete": pairs == manifest["test"]["total_tasks"],
        "protocol": manifest["protocol"],
        "pairs": pairs,
        "scratch_success_rate": totals["scratch_correct"] / pairs if pairs else None,
        "routed_success_rate": totals["routed_correct"] / pairs if pairs else None,
        "success_rate_delta": (
            (totals["routed_correct"] - totals["scratch_correct"]) / pairs if pairs else None
        ),
        "scratch_mean_steps": totals["scratch_steps"] / pairs if pairs else None,
        "routed_mean_steps": totals["routed_steps"] / pairs if pairs else None,
        **{key: value for key, value in totals.items() if key != "pairs"},
        "route_decisions": decisions,
        "by_route": by_route,
        "by_site": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "aggregate"])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dataset")
    parser.add_argument("--results-root")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.command == "validate":
        if not args.dataset:
            raise SystemExit("validate requires --dataset")
        errors = validate_manifest(args.manifest, load(args.dataset))
        print("valid" if not errors else "\n".join(errors))
        return bool(errors)
    if not args.results_root:
        raise SystemExit("aggregate requires --results-root")
    report = aggregate(args.manifest, args.results_root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
