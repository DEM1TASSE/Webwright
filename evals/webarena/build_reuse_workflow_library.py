#!/usr/bin/env python3
"""Build one frozen, pre-primitive workflow skill per eligible TRAIN template."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def eligible_templates(split, by_template):
    for site, rows in split["train"].items():
        for row in rows:
            if not row.get("workflow_skill"):
                continue
            template_id = str(row["intent_template_id"])
            yield site, template_id, list(by_template.get(site, {}).get(template_id, []))


def built_skill_ids(library, source_dir):
    """Resolve the opaque distilled skill id back to this frozen template's source runs."""
    ledger_path = Path(library) / ".learned.json"
    if not ledger_path.exists():
        return []
    source_runs = {os.path.realpath(path) for path in Path(source_dir).iterdir() if path.is_dir()}
    templates = {
        row.get("template")
        for run, row in (load(ledger_path).get("runs") or {}).items()
        if os.path.realpath(run) in source_runs and row.get("template")
    }
    skill_ids = []
    for meta_path in Path(library).glob("*/meta.json"):
        if load(meta_path).get("template") in templates:
            skill_ids.append(meta_path.parent.name)
    return sorted(skill_ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--by-template", required=True)
    ap.add_argument("--frozen-worktree", required=True)
    ap.add_argument("--expected-commit", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--work-root", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument("--verify", choices=["off", "shape", "strict"], default="strict")
    ap.add_argument("--min-gold-sources", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    frozen = Path(args.frozen_worktree).resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=frozen, text=True
    ).strip()
    if commit != args.expected_commit:
        raise SystemExit(f"frozen workflow commit mismatch: {commit}")

    split, manifests = load(args.split), load(args.by_template)
    model = (yaml.safe_load(Path(args.model_config).read_text(encoding="utf-8")) or {}).get("model")
    if not isinstance(model, dict) or not model.get("model_name"):
        raise SystemExit(f"invalid model config: {args.model_config}")
    work_root, library = Path(args.work_root), Path(args.library)
    events = []
    for site, template_id, records in eligible_templates(split, manifests):
        site_library = library / site
        event = {"site": site, "template_id": int(template_id), "gold_sources": len(records)}
        if len(records) < args.min_gold_sources:
            event["status"] = "insufficient_gold_sources"
            events.append(event)
            continue
        source_dir = work_root / site / f"template_{template_id}" / "runs"
        source_dir.mkdir(parents=True, exist_ok=True)
        golds = {}
        for record_path in records:
            record = load(record_path)
            run_dir = Path(record["run_dir"]).resolve()
            task_id = int(record["task_id"])
            target = source_dir / run_dir.name
            if not target.exists():
                target.symlink_to(run_dir, target_is_directory=True)
            golds[str(task_id)] = record["answer"]
        gold_path = source_dir.parent / "golds.json"
        gold_path.write_text(json.dumps(golds, ensure_ascii=False, indent=2) + "\n")
        cmd = [
            sys.executable, "-m", "webwright.skill_factory.learn", str(source_dir),
            "--library", str(site_library), "--golds", str(gold_path), "--chunk", "25",
            "--verify", args.verify, "--on-fail", "reference",
        ]
        event["command"] = cmd
        if args.dry_run:
            event["status"] = "planned"
        else:
            env = os.environ.copy()
            old_path = env.get("PYTHONPATH")
            env["PYTHONPATH"] = str(frozen / "src") + (os.pathsep + old_path if old_path else "")
            env["SKILL_MODEL_CLASS"] = str(model.get("model_class", "openai"))
            env["SKILL_MODEL_NAME"] = str(model["model_name"])
            if model.get("openai_endpoint"):
                env["SKILL_MODEL_ENDPOINT"] = str(model["openai_endpoint"])
            env["SKILL_MODEL_TIMEOUT"] = str(model.get("request_timeout_seconds", 600))
            proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
            event.update(status="built" if proc.returncode == 0 else "failed",
                         returncode=proc.returncode, stdout=proc.stdout[-4000:],
                         stderr=proc.stderr[-4000:])
            if proc.returncode == 0:
                event["skill_ids"] = built_skill_ids(site_library, source_dir)
        events.append(event)
        work_root.mkdir(parents=True, exist_ok=True)
        (work_root / "build_events.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2) + "\n"
        )
    summary = {
        "frozen_commit": commit,
        "templates": len(events),
        "built": sum(x["status"] == "built" for x in events),
        "insufficient_gold_sources": sum(
            x["status"] == "insufficient_gold_sources" for x in events
        ),
        "failed": sum(x["status"] == "failed" for x in events),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return int(summary["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
