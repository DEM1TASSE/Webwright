#!/usr/bin/env python3
"""Gold-gate TRAIN results and emit auditable site/template build manifests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prepare(split_path, results_root):
    split = load(split_path)
    by_site = {}
    by_template = {}
    attempted = admitted = 0
    for site, rows in split["train"].items():
        site_paths = []
        site_templates = {}
        for row in rows:
            template_id = row["intent_template_id"]
            template_paths = []
            for task_id in row["build_task_ids"]:
                attempted += 1
                path = Path(results_root) / site / f"task{task_id}_scratch.json"
                if not path.exists():
                    continue
                record = load(path)
                if (record.get("task_id") != task_id or record.get("site") != site
                        or record.get("intent_template_id") != template_id):
                    raise ValueError(f"{path}: result identity does not match frozen split")
                if record.get("retrieved_primitives"):
                    raise ValueError(f"{path}: TRAIN result consumed primitive material")
                if record.get("correct") is not True or record.get("score") != 1.0:
                    continue
                run_dir = Path(record.get("run_dir") or "")
                if not (run_dir / "final_script.py").is_file():
                    raise ValueError(f"{path}: admitted result lacks final_script.py")
                resolved = str(path.resolve())
                template_paths.append(resolved)
                site_paths.append(resolved)
                admitted += 1
            site_templates[str(template_id)] = template_paths
        by_site[site] = site_paths
        by_template[site] = site_templates
    return {
        "attempted": attempted,
        "admitted": admitted,
        "by_site": by_site,
        "by_template": by_template,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    result = prepare(args.split, args.results_root)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for name in ("by_site", "by_template"):
        (output / f"{name}.json").write_text(
            json.dumps(result[name], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    summary = {"attempted": result["attempted"], "admitted": result["admitted"],
               "sites": {site: len(paths) for site, paths in result["by_site"].items()}}
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
