#!/usr/bin/env python3
"""Validate a frozen WebVoyager source/held-out manifest against official task data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from webwright.skill_factory.webvoyager_eval import load_task_map


def validate(manifest, tasks):
    errors, seen, summary = [], {}, {"sites": {}, "task_count": 0}
    for site, spec in (manifest.get("sites") or {}).items():
        site_summary = {"source": 0, "heldout": 0, "family_overlap": [],
                        "capability_overlap": []}
        families, capabilities = {}, {}
        for arm in ("source", "heldout"):
            families[arm], capabilities[arm] = set(), set()
            rows = spec.get(arm) or []
            site_summary[arm] = len(rows); summary["task_count"] += len(rows)
            for row in rows:
                task_id = str(row.get("task_id") or "")
                family = str(row.get("family_id") or "")
                caps = {str(value) for value in row.get("capabilities") or [] if value}
                if not task_id or not family:
                    errors.append(f"{site}/{arm}: task_id and family_id are required")
                    continue
                if task_id in seen:
                    errors.append(f"duplicate task_id {task_id}: {seen[task_id]} and {site}/{arm}")
                seen[task_id] = f"{site}/{arm}"
                task = tasks.get(task_id)
                if task is None:
                    errors.append(f"{site}/{arm}: unknown task_id {task_id}")
                elif task.get("web_name") != site:
                    errors.append(f"{task_id}: dataset site {task.get('web_name')!r} != {site!r}")
                families[arm].add(family); capabilities[arm].update(caps)
        site_summary["family_overlap"] = sorted(families["source"] & families["heldout"])
        site_summary["capability_overlap"] = sorted(
            capabilities["source"] & capabilities["heldout"]
        )
        summary["sites"][site] = site_summary
    return {"valid": not errors, "errors": errors, "summary": summary}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    result = validate(manifest, load_task_map(args.dataset))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

