#!/usr/bin/env python3
"""Build auditable candidate site packages from gold WebArena workflows."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

from webwright.skill_factory.audited_primitive_build import (
    build_audited_site_library,
    write_candidate_review,
)
from webwright.skill_factory.llm import configure_llm, llm_json
from generate_site_package_candidates import clean_workflow, load


def compact_behavior_feedback(value):
    """Keep release-relevant counterexamples without re-injecting large page dumps."""
    if not isinstance(value, dict):
        return value
    compact = {}
    for name, row in value.items():
        if not isinstance(row, dict):
            compact[name] = row
            continue
        item = {"ok": bool(row.get("ok"))}
        if row.get("ok"):
            result = row.get("value")
            if isinstance(result, dict):
                item["value_summary"] = {
                    key: child for key, child in result.items()
                    if key in {
                        "duration_seconds", "duration_text", "distance_text",
                        "distance_meters", "acquisition_mode", "travel_mode",
                        "transport_mode", "raw_summary_text_present", "document_status",
                    } and isinstance(child, (str, int, float, bool, type(None)))
                }
                for collection_key in ("results", "places"):
                    rows = result.get(collection_key)
                    if isinstance(rows, list):
                        item["value_summary"][collection_key + "_count"] = len(rows)
                        if rows and isinstance(rows[0], dict):
                            item["value_summary"][collection_key + "_fields"] = sorted(rows[0])
            else:
                item["value_summary"] = str(result)[:500]
        else:
            item["error"] = str(row.get("error") or "")[:2000]
            if row.get("page_url"):
                item["page_url"] = str(row["page_url"])
            controls, seen = [], set()
            for control in row.get("control_diagnostics") or []:
                if not isinstance(control, dict):
                    continue
                normalized = {
                    key: control.get(key) for key in (
                        "tag", "id", "name", "type", "placeholder", "aria_label"
                    ) if control.get(key) is not None
                }
                signature = tuple(sorted(normalized.items()))
                if normalized and signature not in seen:
                    seen.add(signature)
                    controls.append(normalized)
            if controls:
                item["control_diagnostics"] = controls[:20]
        compact[name] = item
    return compact


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument(
        "--workers", type=int, default=16,
        help="Parallel workflow-extraction and independent induction-batch workers.",
    )
    parser.add_argument(
        "--site-workers", type=int, default=4,
        help="Websites to build concurrently; consolidation remains serial within each website.",
    )
    parser.add_argument("--seed", type=int, default=20260810)
    parser.add_argument("--sites", nargs="*", help="Optional site subset for resumable builds")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--verification-profile", choices=["minimal", "strict"], default="strict",
        help="minimal keeps executable shape/identity/provenance; strict adds semantic quality policy.",
    )
    parser.add_argument(
        "--max-output-tokens", type=int, default=24000,
        help="Maximum tokens for each extraction/update/quality response.",
    )
    parser.add_argument(
        "--force-consolidation", action="store_true",
        help="Reuse accepted extraction/batch snapshots but rerun consolidation and rendering.",
    )
    parser.add_argument(
        "--behavior-feedback",
        help="Optional JSON from a package behavior smoke; failed probes guide consolidation retry.",
    )
    parser.add_argument(
        "--rebuild-from-batch", type=int,
        help="Reuse earlier accepted batch snapshots and regenerate this batch and all later ones.",
    )
    parser.add_argument(
        "--model-config", required=True,
        help="Webwright YAML containing an explicit top-level model mapping.",
    )
    args = parser.parse_args()
    behavior_feedback = (
        compact_behavior_feedback(load(args.behavior_feedback))
        if args.behavior_feedback else None
    )
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
    selected = [(site, workflows) for site, workflows in sorted(by_site.items())
                if not args.sites or site in set(args.sites)]

    def build_one(site, workflows):
        existing_index = Path(args.output) / site / "final_candidate" / "index.json"
        if (existing_index.exists() and not args.force_consolidation
                and args.rebuild_from_batch is None):
            existing = load(existing_index)
            write_candidate_review(
                existing_index.parent, site=site, primitives=existing.get("primitives") or []
            )
            return site, {
                "site": site, "status": existing.get("status", "candidate"),
                "resumed": True, "package": str(existing_index.parent / "package.py"),
            }
        result = build_audited_site_library(
            site=site, workflows=workflows, output=Path(args.output) / site,
            batch_size=args.batch_size, seed=args.seed,
            llm_fn=lambda system, user: llm_json(
                system, user, max_tokens=args.max_output_tokens
            ),
            max_attempts=args.max_attempts,
            rebuild_from_batch=args.rebuild_from_batch,
            max_workers=args.workers,
            behavior_smoke_feedback=(
                behavior_feedback.get(site)
                if isinstance(behavior_feedback, dict) and site in behavior_feedback
                else behavior_feedback
            ),
            verification_profile=args.verification_profile,
        )
        return site, result

    failures = {}
    with ThreadPoolExecutor(max_workers=max(1, min(args.site_workers, len(selected) or 1))) as pool:
        futures = {pool.submit(build_one, site, workflows): site
                   for site, workflows in selected}
        for future in as_completed(futures):
            site = futures[future]
            try:
                _, result = future.result()
                summary["sites"][site] = result
            except Exception as exc:
                failures[site] = f"{type(exc).__name__}: {exc}"
                summary["sites"][site] = {
                    "site": site, "status": "failed", "error": failures[site],
                }
    if failures:
        summary["status"] = "partial_failure"
    summary["sites"] = dict(sorted(summary["sites"].items()))
    Path(args.output).mkdir(parents=True, exist_ok=True)
    (Path(args.output) / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    if failures:
        raise RuntimeError(f"site builds failed: {failures}")


if __name__ == "__main__":
    main()
