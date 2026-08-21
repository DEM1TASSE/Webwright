#!/usr/bin/env python3
"""Hash and freeze pipeline-generated Primitive and Workflow libraries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SITES = {"gitlab", "map", "reddit", "shopping", "shopping_admin", "wikipedia"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path: Path) -> dict:
    files = {str(item.relative_to(path)): sha(item) for item in sorted(path.rglob("*")) if item.is_file()}
    digest = hashlib.sha256("".join(f"{name}\0{value}\n" for name, value in files.items()).encode()).hexdigest()
    return {"sha256": digest, "file_count": len(files), "files": files}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--primitive-library", required=True)
    ap.add_argument("--workflow-library", required=True)
    ap.add_argument("--workflow-events", required=True)
    ap.add_argument("--builder-commit", required=True)
    ap.add_argument("--evaluation-commit", required=True)
    ap.add_argument("--input", action="append", default=[])
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    primitive = Path(args.primitive_library).resolve()
    workflow = Path(args.workflow_library).resolve()
    events_path = Path(args.workflow_events).resolve()
    primitive_counts = {}
    for site in sorted(SITES):
        site_root = primitive / site
        config = load(site_root / "config.json")
        audit = load(site_root / "audit.json")
        index = load(site_root / "final_candidate/index.json")
        package = site_root / "final_candidate/package.py"
        compile(package.read_text(encoding="utf-8"), str(package), "exec")
        if config.get("verification_profile") != "minimal" or index.get("verification_profile") != "minimal":
            raise SystemExit(f"{site}: not generated with minimal verification")
        if audit.get("status") != "candidate" or index.get("status") != "candidate":
            raise SystemExit(f"{site}: incomplete primitive build")
        ids = [row.get("primitive_id") for row in index.get("primitives") or []]
        if len(ids) != len(set(ids)):
            raise SystemExit(f"{site}: duplicate primitive ids")
        primitive_counts[site] = len(ids)

    events = load(events_path)
    built = [row for row in events if row.get("status") == "built"]
    keys = {(row.get("site"), int(row.get("template_id"))) for row in built}
    if len(built) != len(keys):
        raise SystemExit("workflow events contain duplicate active templates")
    source_grades = {"reference": 0, "refined": 0, "generalized": 0}
    for row in built:
        skill_ids = row.get("skill_ids") or []
        if len(skill_ids) != 1:
            raise SystemExit("built workflow must identify exactly one skill")
        root = workflow / row["site"] / skill_ids[0]
        meta = load(root / "meta.json")
        compile((root / "skill.py").read_text(encoding="utf-8"), str(root / "skill.py"), "exec")
        if meta.get("pipeline_profile") != "minimal" or not meta.get("active_for_hint"):
            raise SystemExit(f"{root}: not an active minimal workflow")
        if meta.get("portability_warnings"):
            raise SystemExit(f"{root}: portability warnings")
        source_grades[meta["source_grade"]] += 1

    inputs = {str(Path(value).resolve()): sha(Path(value).resolve()) for value in args.input}
    manifest = {
        "schema_version": 1,
        "generated_only": True,
        "builder_commit": args.builder_commit,
        "evaluation_commit": args.evaluation_commit,
        "primitive": {"path": str(primitive), "profile": "minimal", "counts": primitive_counts,
                      "total": sum(primitive_counts.values()), "tree": tree(primitive)},
        "workflow": {"path": str(workflow), "profile": "minimal", "built": len(built),
                     "source_grades": source_grades, "tree": tree(workflow)},
        "workflow_events": {"path": str(events_path), "sha256": sha(events_path)},
        "inputs": inputs,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"primitive": manifest["primitive"]["total"], "workflow": len(built),
                      "manifest_sha256": sha(output)}))


if __name__ == "__main__":
    main()
