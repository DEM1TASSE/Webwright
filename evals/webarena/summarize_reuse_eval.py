#!/usr/bin/env python3
"""Validate and summarize the frozen T1/T2 reuse evaluation."""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ARMS = {"t1": ("scratch", "workflow"), "t2": ("scratch", "workflow", "primitive")}
TERMINAL = {"scored_correct", "scored_incorrect", "agent_timeout_or_incomplete"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tasks(split, partition):
    rows = []
    source = split["train"] if partition == "t1" else split["test"]
    key = "t1_heldout_task_ids" if partition == "t1" else "t2_task_ids"
    for site, groups in source.items():
        for group in groups:
            rows.extend((site, group["intent_template_id"], task_id)
                        for task_id in group.get(key, []))
    return rows


def mean(values):
    return round(statistics.mean(values), 3) if values else None


def arm_summary(records):
    terminal = [row for row in records if row.get("run_status") in TERMINAL]
    correct = [row for row in terminal if row.get("correct") is True]
    wrong = [row for row in terminal if row.get("correct") is False]
    route = Counter(row.get("route_decision") or "none" for row in terminal)
    template_groups = defaultdict(list)
    for row in terminal:
        template_groups[(row["site"], row["intent_template_id"])].append(row)
    sites = {}
    for site in sorted({row["site"] for row in terminal}):
        subset = [row for row in terminal if row["site"] == site]
        sites[site] = {
            "n": len(subset), "correct": sum(row.get("correct") is True for row in subset),
            "accuracy": round(sum(row.get("correct") is True for row in subset) / len(subset), 4),
            "mean_steps": mean([row["steps"] for row in subset if row.get("steps") is not None]),
        }
    return {
        "n": len(records), "terminal": len(terminal), "correct": len(correct),
        "accuracy": round(len(correct) / len(terminal), 4) if terminal else None,
        "templates": len(template_groups),
        "macro_template_accuracy": mean([
            sum(row.get("correct") is True for row in group) / len(group)
            for group in template_groups.values()
        ]),
        "timeouts_or_incomplete": sum(row.get("run_status") == "agent_timeout_or_incomplete"
                                      for row in terminal),
        "mean_steps": mean([row["steps"] for row in terminal if row.get("steps") is not None]),
        "mean_steps_correct": mean([row["steps"] for row in correct if row.get("steps") is not None]),
        "mean_steps_wrong": mean([row["steps"] for row in wrong if row.get("steps") is not None]),
        "route_decisions": dict(sorted(route.items())),
        "primitive_exposed": sum(bool(row.get("retrieved_primitives")) for row in terminal),
        "primitive_code_incorporated": sum(
            bool(row.get("code_incorporated_primitives")) for row in terminal),
        "primitive_usage_declared": sum(
            bool(row.get("declared_used_primitives")) for row in terminal),
        "primitive_execution_traced": sum(bool(row.get("primitive_execution_trace"))
                                          for row in terminal),
        "by_site": sites,
    }


def paired_stats(pairs):
    outcomes = Counter()
    deltas = []
    both_correct_deltas = []
    task_ids = defaultdict(list)
    templates = defaultdict(list)
    for left, right in pairs:
        lc, rc = left.get("correct") is True, right.get("correct") is True
        outcome = "win" if rc and not lc else "loss" if lc and not rc else (
            "both_correct" if lc else "both_wrong")
        outcomes[outcome] += 1
        task_ids[outcome].append(right["task_id"])
        templates[(right["site"], right["intent_template_id"])].append((lc, rc))
        if left.get("steps") is not None and right.get("steps") is not None:
            delta = right["steps"] - left["steps"]
            deltas.append(delta)
            if lc and rc:
                both_correct_deltas.append(delta)
    return {
        "pairs": len(pairs), **{name: outcomes[name] for name in
                                ("win", "loss", "both_correct", "both_wrong")},
        "net_wins": outcomes["win"] - outcomes["loss"],
        "mean_treatment_minus_scratch_steps": mean(deltas),
        "mean_step_delta_when_both_correct": mean(both_correct_deltas),
        "mean_template_accuracy_delta": mean([
            statistics.mean(int(rc) - int(lc) for lc, rc in group)
            for group in templates.values()
        ]),
        "win_task_ids": task_ids["win"],
        "loss_task_ids": task_ids["loss"],
    }


def paired(base, treatment):
    pairs = [(base[key], treatment[key]) for key in sorted(base.keys() & treatment.keys())
             if base[key].get("run_status") in TERMINAL
             and treatment[key].get("run_status") in TERMINAL]
    result = paired_stats(pairs)
    result["by_site"] = {
        site: paired_stats([pair for pair in pairs if pair[1]["site"] == site])
        for site in sorted({pair[1]["site"] for pair in pairs})
    }
    result["by_route_decision"] = {
        decision: paired_stats([
            pair for pair in pairs if (pair[1].get("route_decision") or "none") == decision
        ])
        for decision in sorted({pair[1].get("route_decision") or "none" for pair in pairs})
    }
    return result


def isolation_errors(row, partition, arm):
    """Return frozen-arm contamination errors for one compact result."""
    errors = []
    label = f"{partition}/{arm}/task{row.get('task_id')}"
    primitives = row.get("retrieved_primitives") or []
    workflow = row.get("routed_workflow_id")
    stage = row.get("route_stage")
    decision = row.get("route_decision")
    if arm == "scratch":
        if stage is not None or decision is not None or primitives or workflow:
            errors.append(f"{label}: scratch arm contains routed material")
    elif arm == "workflow":
        if stage != "workflow" or primitives or row.get("primitive_metadata_only"):
            errors.append(f"{label}: workflow arm isolation violated")
        if decision in {"use", "adapt"} and not workflow:
            errors.append(f"{label}: selected workflow is missing")
        if decision == "skip" and workflow:
            errors.append(f"{label}: skipped workflow was injected")
    elif arm == "primitive":
        if stage != "primitive" or workflow:
            errors.append(f"{label}: primitive arm isolation violated")
        if decision in {"use", "adapt"} and not primitives:
            errors.append(f"{label}: selected primitive code is missing")
        if decision == "skip" and primitives:
            errors.append(f"{label}: skipped primitives were injected")
    return errors


def routing_comparison(indexed, audit_root):
    audit = []
    for path in sorted(Path(audit_root).glob("*.json")):
        if path.name != "summary.json":
            audit.extend(load(path))
    mismatches = []
    selection_mismatches = []
    compared = 0
    for expected in audit:
        key = f"{expected['partition']}/{expected['arm']}"
        actual = indexed.get(key, {}).get(expected["task_id"])
        if actual is None:
            continue
        compared += 1
        if expected["decision"] != actual.get("route_decision"):
            mismatches.append({
                "partition": expected["partition"], "arm": expected["arm"],
                "task_id": expected["task_id"], "audit": expected["decision"],
                "e2e": actual.get("route_decision"),
            })
        audit_ids = expected.get("primitive_ids") or (
            [expected["skill_id"]] if expected.get("skill_id") else [])
        actual_ids = ([item["primitive_id"] for item in actual.get("retrieved_primitives", [])]
                      if expected["arm"] == "primitive" else
                      ([actual["routed_workflow_id"]]
                       if actual.get("routed_workflow_id") else []))
        if audit_ids != actual_ids:
            selection_mismatches.append({
                "partition": expected["partition"], "arm": expected["arm"],
                "task_id": expected["task_id"], "audit": audit_ids, "e2e": actual_ids,
            })
    return {
        "compared": compared,
        "decision_matches": compared - len(mismatches),
        "decision_mismatches": mismatches,
        "selection_matches": compared - len(selection_mismatches),
        "selection_mismatches": selection_mismatches,
    }


def summarize(split, results_root, retrieval_audit=None):
    root = Path(results_root)
    result = {"valid": True, "expected_records": 0, "found_records": 0,
              "missing": [], "identity_errors": [], "status_errors": [],
              "isolation_errors": [], "arms": {}, "paired": {}}
    indexed = {}
    for partition, arms in ARMS.items():
        expected = tasks(split, partition)
        for arm in arms:
            records, by_id = [], {}
            for site, template_id, task_id in expected:
                path = root / partition / arm / site / f"task{task_id}_{arm}.json"
                result["expected_records"] += 1
                if not path.is_file():
                    result["missing"].append(str(path))
                    continue
                row = load(path)
                result["found_records"] += 1
                if (row.get("task_id"), row.get("site"), row.get("intent_template_id")) != (
                        task_id, site, template_id):
                    result["identity_errors"].append(str(path))
                if row.get("run_status") not in TERMINAL:
                    result["status_errors"].append(
                        f"{path}: {row.get('run_status') or 'missing run_status'}")
                result["isolation_errors"].extend(isolation_errors(row, partition, arm))
                records.append(row)
                by_id[task_id] = row
            key = f"{partition}/{arm}"
            result["arms"][key] = arm_summary(records)
            indexed[key] = by_id
        base = indexed[f"{partition}/scratch"]
        for arm in arms[1:]:
            result["paired"][f"{partition}/{arm}_vs_scratch"] = paired(
                base, indexed[f"{partition}/{arm}"])
    result["valid"] = not any(result[name] for name in
                              ("missing", "identity_errors", "status_errors",
                               "isolation_errors"))
    if retrieval_audit:
        result["routing_audit_vs_e2e"] = routing_comparison(indexed, retrieval_audit)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", required=True)
    parser.add_argument("--results-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--retrieval-audit")
    args = parser.parse_args()
    result = summarize(load(args.split), args.results_root, args.retrieval_audit)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(not result["valid"])


if __name__ == "__main__":
    raise SystemExit(main())
