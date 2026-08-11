"""Freeze the gold source workflows into a self-contained snapshot.

The scripted pipeline resolved its inputs at build time from a manifest of result JSONs that
point at ``<run_dir>/final_script.py``. Those run directories are untracked eval artifacts, so a
build was only reproducible on the machine that produced them. This writes the resolved
workflows — code inlined — to ``inputs/workflows/<site>.json`` plus a provenance manifest, so the
agentic build runs from a fixed, diffable input set.

Two sources:

    # from an existing audited library's staged stage-1 inputs
    python -m skill_agent.tools.snapshot_inputs --from-library <library_dir> --output <dir>

    # from the original manifest + dataset
    python -m skill_agent.tools.snapshot_inputs --manifest m.json --dataset d.json --output <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

_WORKFLOW_FIELDS = ("id", "task_id", "template_id", "intent", "site", "code", "record_path")


def _dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clean(workflow: dict) -> dict:
    missing = [f for f in _WORKFLOW_FIELDS if f not in workflow and f != "record_path"]
    if missing:
        raise ValueError(f"workflow {workflow.get('id')!r} is missing {missing}")
    return {field: workflow.get(field) for field in _WORKFLOW_FIELDS}


def from_library(library: Path) -> dict[str, list[dict]]:
    """Harvest the workflow records an audited build staged into extractions/<id>/input.json."""
    by_site: dict[str, list[dict]] = defaultdict(list)
    for site_dir in sorted(p for p in library.iterdir() if p.is_dir()):
        # Rejected/failed development runs are kept as siblings; they are not sources.
        if any(marker in site_dir.name for marker in ("rejected", "failed", "pre_")):
            continue
        for input_path in sorted(site_dir.glob("extractions/*/input.json")):
            record = json.loads(input_path.read_text(encoding="utf-8"))
            workflow = _clean(record["workflow"])
            if workflow["site"] != site_dir.name:
                raise ValueError(f"{input_path}: site mismatch {workflow['site']} != {site_dir.name}")
            by_site[site_dir.name].append(workflow)
    return dict(by_site)


def from_manifest(manifest: Path, dataset: Path, evals_dir: Path) -> dict[str, list[dict]]:
    sys.path.insert(0, str(evals_dir))
    from generate_site_package_candidates import clean_workflow, load  # noqa: E402

    rows = load(dataset)
    by_site: dict[str, list[dict]] = defaultdict(list)
    for declared_site, paths in load(manifest).items():
        for path in paths:
            workflow = clean_workflow(path, rows)
            if workflow["site"] != declared_site:
                raise ValueError(f"{path}: declared site does not match dataset site")
            by_site[declared_site].append(_clean(workflow))
    return dict(by_site)


def write_snapshot(by_site: dict[str, list[dict]], output: Path, source: str) -> dict:
    manifest = {"source": source, "sites": {}}
    for site, workflows in sorted(by_site.items()):
        workflows = sorted(workflows, key=lambda x: (x.get("template_id") or 0, x.get("task_id") or 0))
        _dump(output / "workflows" / f"{site}.json", workflows)
        manifest["sites"][site] = {
            "workflow_count": len(workflows),
            "workflows": [{
                "id": w["id"], "task_id": w["task_id"], "template_id": w["template_id"],
                "record_path": w.get("record_path") or "",
                "code_sha256": "sha256:" + hashlib.sha256(w["code"].encode()).hexdigest(),
            } for w in workflows],
        }
    manifest["total_workflows"] = sum(v["workflow_count"] for v in manifest["sites"].values())
    _dump(output / "MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-library", help="An audited library directory to harvest from")
    parser.add_argument("--manifest", help="site -> [result json paths]")
    parser.add_argument("--dataset", help="WebArena dataset json")
    parser.add_argument("--evals-dir", default="evals/webarena",
                        help="Directory holding generate_site_package_candidates.py")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    if args.from_library:
        by_site = from_library(Path(args.from_library))
        source = f"library:{args.from_library}"
    elif args.manifest and args.dataset:
        by_site = from_manifest(Path(args.manifest), Path(args.dataset), Path(args.evals_dir))
        source = f"manifest:{args.manifest}"
    else:
        parser.error("pass --from-library, or both --manifest and --dataset")

    manifest = write_snapshot(by_site, Path(args.output), source)
    print(json.dumps({"output": args.output, "total_workflows": manifest["total_workflows"],
                      "sites": {k: v["workflow_count"] for k, v in manifest["sites"].items()}},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
