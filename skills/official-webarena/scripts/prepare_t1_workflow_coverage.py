#!/usr/bin/env python3
"""Freeze the exact T1 subset covered by pipeline-built workflows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--parallel", required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--replay", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    built = {
        (str(row["site"]), int(row["template_id"]))
        for row in load(args.events)
        if row.get("status") == "built" and len(row.get("skill_ids") or []) == 1
    }
    jobs = []
    for site, rows in load(args.split)["train"].items():
        for row in rows:
            template_id = int(row["intent_template_id"])
            for task_id in row.get("t1_heldout_task_ids") or []:
                jobs.append({"site": site, "template_id": template_id, "task_id": int(task_id)})
    covered = [row for row in jobs if (row["site"], row["template_id"]) in built]
    missing = [row for row in jobs if (row["site"], row["template_id"]) not in built]
    parallel = {int(value) for value in load(args.parallel)}
    serial = {int(value) for value in load(args.serial)}
    replay = {int(value) for value in load(args.replay)}
    covered_ids = {row["task_id"] for row in covered}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write(output / "covered_ids.json", sorted(covered_ids))
    write(output / "missing_ids.json", sorted(row["task_id"] for row in missing))
    write(output / "covered_parallel_ids.json", sorted(covered_ids & parallel))
    write(output / "covered_serial_ids.json", sorted(covered_ids & serial))
    write(output / "covered_replay_ids.json", sorted(covered_ids & replay))
    summary = {
        "heldout": len(jobs), "covered": len(covered), "missing": len(missing),
        "covered_parallel": len(covered_ids & parallel),
        "covered_serial": len(covered_ids & serial), "missing_jobs": missing,
        "covered_replay": len(covered_ids & replay),
    }
    write(output / "coverage.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "missing_jobs"}))


if __name__ == "__main__":
    main()
