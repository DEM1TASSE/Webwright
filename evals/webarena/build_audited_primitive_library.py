#!/usr/bin/env python3
"""Build auditable candidate site packages from gold WebArena workflows."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml

from webwright.skill_factory.audited_primitive_build import (
    build_audited_site_library,
    write_candidate_review,
)
from webwright.skill_factory.llm import configure_llm, llm_json
from generate_site_package_candidates import clean_workflow, load


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260810)
    parser.add_argument("--sites", nargs="*", help="Optional site subset for resumable builds")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--model-config", required=True,
        help="Webwright YAML containing an explicit top-level model mapping.",
    )
    args = parser.parse_args()
    model_config = yaml.safe_load(Path(args.model_config).read_text(encoding="utf-8")) or {}
    if not isinstance(model_config.get("model"), dict):
        raise ValueError(f"{args.model_config}: missing model configuration")
    configure_llm(model_config["model"])
    dataset, by_site = load(args.dataset), defaultdict(list)
    for site, paths in load(args.manifest).items():
        for path in paths:
            workflow = clean_workflow(path, dataset)
            if workflow["site"] != site:
                raise ValueError(f"{path}: site mismatch")
            by_site[site].append(workflow)
    summary = {"status": "candidate", "promoted": False, "sites": {}}
    for site, workflows in sorted(by_site.items()):
        if args.sites and site not in set(args.sites):
            continue
        existing_index = Path(args.output) / site / "final_candidate" / "index.json"
        if existing_index.exists():
            existing = load(existing_index)
            write_candidate_review(
                existing_index.parent, site=site, primitives=existing.get("primitives") or []
            )
            summary["sites"][site] = {
                "site": site, "status": existing.get("status", "candidate"),
                "resumed": True, "package": str(existing_index.parent / "package.py"),
            }
            continue
        result = build_audited_site_library(
            site=site, workflows=workflows, output=Path(args.output) / site,
            batch_size=args.batch_size, seed=args.seed,
            llm_fn=lambda system, user: llm_json(system, user, max_tokens=24000),
            max_attempts=args.max_attempts,
        )
        summary["sites"][site] = result
    Path(args.output).mkdir(parents=True, exist_ok=True)
    (Path(args.output) / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
