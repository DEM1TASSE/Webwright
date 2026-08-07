#!/usr/bin/env python3
"""Materialize manifests for gold-admitted train results in a frozen split."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect(manifest_path, results_root):
    manifest_path = Path(manifest_path)
    manifest = load(manifest_path)
    by_site = {}
    selected = {}
    for site, relative in manifest["sites"].items():
        split = load(manifest_path.parent / relative)
        task_ids = split["source"]["task_ids"]
        selected[site] = len(task_ids)
        paths = []
        for task_id in task_ids:
            path = Path(results_root) / site / f"task{task_id}_scratch.json"
            record = load(path)
            if record.get("task_id") != task_id or record.get("site") != site:
                raise ValueError(f"{path}: result identity mismatch")
            if record.get("score") == 1.0 and record.get("correct") is True:
                if record.get("retrieved_primitives"):
                    raise ValueError(f"{path}: train source consumed primitive material")
                paths.append(str(path))
        by_site[site] = paths
    return by_site, selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--results-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    by_site, selected = collect(args.manifest, args.results_root)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "by_site.json").write_text(
        json.dumps(by_site, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    flat = [path for site in by_site.values() for path in site]
    (output / "all.json").write_text(
        json.dumps(flat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for site, paths in by_site.items():
        (output / f"{site}.json").write_text(
            json.dumps(paths, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output / f"{site}.primitive.json").write_text(
            json.dumps({site: paths}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    report = {
        site: {"selected": selected[site], "gold_admitted": len(paths)}
        for site, paths in by_site.items()
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
