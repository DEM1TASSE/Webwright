#!/usr/bin/env python3
"""Build audited site libraries from rubric-admitted Odysseys scratch runs."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml

from site_primitives import load_segments
from webwright.skill_factory.audited_primitive_build import (
    build_audited_site_library, write_candidate_review,
)
from webwright.skill_factory.llm import configure_llm, llm_json


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def judge_scores(path: str | Path) -> dict[str, dict[str, int]]:
    payload = load_json(path)
    return {
        str(row["task_id"]): {str(key): int(value)
                              for key, value in (row.get("rubric_scores") or {}).items()}
        for row in payload.get("tasks", [])
    }


def has_source_script(run_dir: Path) -> bool:
    return (run_dir / "final_script.py").is_file() or (
        run_dir.parent.parent / "final_script.py").is_file()


def admitted_workflows(source_manifest: str | Path, judge_results: str | Path) -> dict[str, list[dict]]:
    """Map successful site segments to the existing audited-builder workflow contract."""
    scores = judge_scores(judge_results)
    by_site = defaultdict(list)
    for source in load_json(source_manifest).get("sources", []):
        task_id = str(source["task_id"])
        if str(source.get("mode") or "scratch") != "scratch":
            raise ValueError(f"{task_id}: primitive-consumer runs cannot be source evidence")
        run_dir = Path(source["run_dir"])
        if not has_source_script(run_dir):
            raise ValueError(f"{task_id}: final_script.py missing from {run_dir}")
        segment_code = source.get("segment_code") or {}
        for segment in load_segments(source["segments"], task_id):
            if segment.site is None:
                continue
            if not segment.template_id:
                raise ValueError(f"{task_id}/{segment.segment_id}: template_id is required")
            if not segment.rubric_ids:
                raise ValueError(f"{task_id}/{segment.segment_id}: site evidence needs rubric_ids")
            code_path = Path(str(segment_code.get(segment.segment_id) or ""))
            if not code_path.is_file():
                raise ValueError(
                    f"{task_id}/{segment.segment_id}: reviewed site-only code_path is required"
                )
            failed = [rid for rid in segment.rubric_ids
                      if scores.get(task_id, {}).get(rid) != 1]
            if failed:
                continue
            by_site[segment.site].append({
                "id": f"{task_id}::{segment.segment_id}",
                "task_id": task_id,
                "template_id": segment.template_id,
                "intent": segment.goal,
                "site": segment.site,
                "code": code_path.read_text(encoding="utf-8"),
                "record_path": str(judge_results),
                "code_path": str(code_path),
                "rubric_ids": list(segment.rubric_ids),
                "source_scope": "site_segment_from_multisite_script",
            })
    return dict(by_site)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--judge-results", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-config", required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--sites", nargs="*", help="Optional canonical site subset")
    parser.add_argument("--resume-preconsolidation", action="store_true")
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.model_config).read_text(encoding="utf-8")) or {}
    if not isinstance(config.get("model"), dict):
        raise ValueError(f"{args.model_config}: missing model configuration")
    workflows = admitted_workflows(args.source_manifest, args.judge_results)
    target = Path(args.output) / "summary.json"
    if target.is_file():
        summary = load_json(target)
        summary["status"] = "candidate"
        summary["source_scope"] = "rubric_admitted_site_segment"
        summary.setdefault("sites", {})
    else:
        summary = {"status": "candidate", "source_scope": "rubric_admitted_site_segment",
                   "sites": {}}
    selected = [(site, rows) for site, rows in sorted(workflows.items())
                if not args.sites or site in set(args.sites)]
    needs_build = any(
        not (Path(args.output) / site / "final_candidate" / "index.json").is_file()
        for site, _ in selected
    )
    if needs_build:
        configure_llm(config["model"])
    for site, rows in selected:
        existing = Path(args.output) / site / "final_candidate" / "index.json"
        if existing.is_file():
            value = load_json(existing)
            summary["sites"][site] = {"site": site, "status": value.get("status"),
                                      "resumed": True}
            continue
        result = build_audited_site_library(
            site=site, workflows=rows, output=Path(args.output) / site,
            batch_size=args.batch_size, seed=args.seed,
            llm_fn=lambda system, user: llm_json(system, user, max_tokens=24000),
            max_attempts=args.max_attempts,
            resume_preconsolidation=args.resume_preconsolidation,
        )
        summary["sites"][site] = result
        index = Path(args.output) / site / "final_candidate" / "index.json"
        if index.is_file():
            value = load_json(index)
            write_candidate_review(index.parent, site=site,
                                   primitives=value.get("primitives") or [])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
