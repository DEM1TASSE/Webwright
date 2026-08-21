#!/usr/bin/env python3
"""Build one workflow from one official WebArena intent_template group.

This file is launched with PYTHONPATH pointing at the frozen pre-primitive Webwright commit.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from webwright.skill_factory.library import Library
from webwright.skill_factory.update import Trace, evolve


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--verify", choices=["off", "shape", "strict"], default="strict")
    ap.add_argument("--source-grade", choices=["reference", "refined", "generalized"],
                    required=True)
    ap.add_argument("--pipeline-profile", choices=["minimal", "strict"], default="strict")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    tasks = {row["task_id"]: row for row in load(args.dataset)}
    records = [load(path) for path in load(args.records)]
    source_tasks = [tasks[row["task_id"]] for row in records]
    template_ids = {task["intent_template_id"] for task in source_tasks}
    templates = {task["intent_template"] for task in source_tasks}
    if len(template_ids) != 1:
        raise ValueError("records must belong to exactly one official template ID")
    canonical_template = (next(iter(templates)) if len(templates) == 1 else
                          "Official WebArena intent_template_id "
                          f"{next(iter(template_ids))} variants: " + " | ".join(sorted(templates)))
    traces = []
    minimal_guidance = (
        "Produce a compact reference-hint workflow, not a debugging harness. Keep the complete "
        "skill at or below 220 lines. Retain only the reusable successful path and small typed "
        "helpers. Omit screenshots, self-reflection, verbose logging, retry frameworks, source-run "
        "artifact management, and benchmark-specific completion gates. Never embed a source "
        "deployment hostname, port, /data path, or auth-state fallback. Read start_url and any "
        "storage_state/auth path only from taskspec/runtime credentials; fail clearly when required "
        "runtime context is absent. Parameterize every instance-specific value from taskspec params."
    )
    for record, task in zip(records, source_tasks):
        run_dir = Path(record["run_dir"])
        run_task = load(run_dir / "task.json")
        start_url = run_task["start_url"]
        task_eval = task.get("eval") or {}
        eval_rows = task_eval if isinstance(task_eval, list) else [task_eval]
        schema = next((item.get("results_schema") for item in eval_rows
                       if isinstance(item, dict)
                       and item.get("evaluator") == "AgentResponseEvaluator"), None)
        traces.append(Trace(
            template=canonical_template,
            code=(run_dir / "final_script.py").read_text(encoding="utf-8"),
            answer=record["answer"], correct=True, verdict="skip",
            meta={"params": task.get("instantiation_dict") or {},
                  "site": urlparse(start_url).netloc,
                  "start_url": start_url, "output_schema": schema,
                  "generation_guidance": (
                      minimal_guidance if args.pipeline_profile == "minimal" else ""
                  )},
        ))
    library = Library(args.library)
    before = {skill.skill_id for skill in library.list()}
    effective_verify = "off" if args.pipeline_profile == "minimal" else args.verify
    log = evolve(
        traces, library, verify=effective_verify,
        rounds=1 if args.pipeline_profile == "minimal" else 2,
        on_fail="reference", draws=1 if args.pipeline_profile == "minimal" else 2,
    )
    matching = [skill.skill_id for skill in library.list()
                if skill.meta.get("template") == canonical_template]
    if len(matching) != 1:
        raise RuntimeError(
            f"template must have exactly one active workflow, found {matching}"
        )
    active = library.get(matching[0])
    active.meta["active"] = True
    active.meta["source_grade"] = args.source_grade
    active.meta["source_count"] = len(records)
    active.meta["pipeline_profile"] = args.pipeline_profile
    active.meta["active_for_hint"] = True
    active.meta["active_for_execution"] = bool(active.meta.get("verified"))
    warnings = []
    if re.search(r"https?://[^\s\"']*gcrsandbox", active.code):
        warnings.append("hardcoded_source_deployment_origin")
    if re.search(r"/data/ww_official/\.auth(?:_inst\d+)?/", active.code):
        warnings.append("hardcoded_source_auth_path")
    active.meta["portability_warnings"] = warnings
    library.add(active)
    output = {"template_id": next(iter(template_ids)), "template": canonical_template,
              "template_variants": sorted(templates),
              "source_task_ids": [row["task_id"] for row in records],
              "pipeline_profile": args.pipeline_profile,
              "effective_verify": effective_verify,
              "portability_warnings": warnings,
              "skill_ids": sorted(matching), "new_skill_ids": sorted(set(matching) - before),
              "evolve": log}
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
