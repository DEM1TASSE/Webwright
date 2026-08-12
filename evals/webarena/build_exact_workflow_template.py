#!/usr/bin/env python3
"""Build one workflow from one official WebArena intent_template group.

This file is launched with PYTHONPATH pointing at the frozen pre-primitive Webwright commit.
"""
from __future__ import annotations

import argparse
import json
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
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    tasks = {row["task_id"]: row for row in load(args.dataset)}
    records = [load(path) for path in load(args.records)]
    source_tasks = [tasks[row["task_id"]] for row in records]
    template_ids = {task["intent_template_id"] for task in source_tasks}
    templates = {task["intent_template"] for task in source_tasks}
    if len(template_ids) != 1 or len(templates) != 1:
        raise ValueError("records must belong to exactly one official template")
    traces = []
    for record, task in zip(records, source_tasks):
        run_dir = Path(record["run_dir"])
        schema = next((item.get("results_schema") for item in task.get("eval", [])
                       if item.get("evaluator") == "AgentResponseEvaluator"), None)
        traces.append(Trace(
            template=task["intent_template"],
            code=(run_dir / "final_script.py").read_text(encoding="utf-8"),
            answer=record["answer"], correct=True, verdict="skip",
            meta={"params": task.get("instantiation_dict") or {},
                  "site": urlparse(task["start_urls"][0]).netloc,
                  "start_url": task["start_urls"][0], "output_schema": schema},
        ))
    library = Library(args.library)
    before = {skill.skill_id for skill in library.list()}
    log = evolve(traces, library, verify=args.verify, rounds=2,
                 on_fail="reference", draws=2)
    matching = [skill.skill_id for skill in library.list()
                if skill.meta.get("template") in templates]
    output = {"template_id": next(iter(template_ids)), "template": next(iter(templates)),
              "source_task_ids": [row["task_id"] for row in records],
              "skill_ids": sorted(matching), "new_skill_ids": sorted(set(matching) - before),
              "evolve": log}
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
