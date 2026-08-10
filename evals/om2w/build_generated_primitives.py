#!/usr/bin/env python3
"""Build a site primitive catalog from WebJudge-admitted OM2W source runs."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from webwright.skill_factory.llm import llm_json
from webwright.skill_factory.om2w_eval import discover_task_dirs, latest_run
from webwright.skill_factory.primitive_catalog import PrimitiveCatalog
from webwright.skill_factory.primitive_update import apply_updates, propose_updates


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def slug(website):
    host = (urlparse(website).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return re.sub(r"[^a-z0-9]+", "_", host).strip("_")


def parse_sources(values):
    result = {}
    for value in values:
        task_id, separator, family = value.partition("=")
        if not separator or not task_id or not family:
            raise ValueError(f"source must be TASK_ID=FAMILY_ID: {value!r}")
        result[task_id] = family
    return result


def admitted_workflows(dataset_path, runs_root, judge_path, sources):
    raw = load_json(dataset_path)
    rows = raw if isinstance(raw, list) else raw.get("tasks", [])
    tasks = {str(row["task_id"]): row for row in rows}
    verdicts = {str(row["task_id"]): row for row in load_jsonl(judge_path)}
    workspaces = discover_task_dirs(runs_root, set(sources))
    workflows = []
    for task_id, family in sources.items():
        if verdicts.get(task_id, {}).get("predicted_label") != 1:
            raise ValueError(f"{task_id}: source is not WebJudge-admitted")
        task = tasks.get(task_id)
        if task is None:
            raise ValueError(f"{task_id}: missing from dataset")
        workspace = workspaces.get(task_id)
        run = latest_run(workspace) if workspace else None
        code_path = run / "final_script.py" if run else None
        if code_path is None or not code_path.is_file():
            raise ValueError(f"{task_id}: latest final run has no final_script.py")
        website = str(task["website"])
        workflows.append({
            "id": f"task{task_id}_{family}", "task_id": task_id,
            "template_id": family,
            "intent": str(task.get("confirmed_task") or task.get("task_description") or ""),
            "site": slug(website), "website": website,
            "code": code_path.read_text(encoding="utf-8"),
            "run_dir": str(run), "judge_record": verdicts[task_id],
        })
    return workflows


def build(workflows, library, report_path, llm_fn=llm_json):
    sites = {row["site"] for row in workflows}
    if len(sites) != 1:
        raise ValueError(f"source workflows span multiple sites: {sorted(sites)}")
    families = {row["template_id"] for row in workflows}
    if len(families) < 2:
        raise ValueError("primitive generation requires at least two source families")
    site = next(iter(sites))
    catalog = PrimitiveCatalog(library, site)
    raw_proposals = []

    def proposer(system, user):
        raw = llm_fn(system, user, max_tokens=16000)
        raw_proposals.append(raw)
        return raw

    operations = propose_updates(site=site, new_workflow=workflows[-1],
                                 peer_workflows=workflows[:-1], catalog=catalog,
                                 llm_fn=proposer)
    applied = apply_updates(catalog, operations,
                            gold_workflows={row["id"] for row in workflows},
                            review_path=Path(report_path).with_suffix(".review.jsonl"))
    report = {
        "library": str(library), "site": site,
        "source_workflows": [{key: row[key] for key in
                              ("id", "task_id", "template_id", "run_dir")}
                             for row in workflows],
        "raw_proposals": raw_proposals, "operations": [vars(op) for op in operations],
        "applied": applied.applied, "reviewed": applied.reviewed,
        "rejected": applied.rejected,
        "active_primitives": [{"primitive_id": item.primitive_id,
                               "content_hash": item.content_hash,
                               "source_templates": item.source_templates,
                               "source_workflows": item.source_workflows}
                              for item in catalog.list()],
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True); parser.add_argument("--runs", required=True)
    parser.add_argument("--judge-results", required=True); parser.add_argument("--library", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--source", action="append", required=True,
                        help="WebJudge-admitted TASK_ID=FAMILY_ID; repeat for each source.")
    args = parser.parse_args()
    workflows = admitted_workflows(args.dataset, args.runs, args.judge_results,
                                   parse_sources(args.source))
    print(json.dumps(build(workflows, args.library, args.report), ensure_ascii=False))


if __name__ == "__main__":
    main()
