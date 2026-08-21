#!/usr/bin/env python3
"""Mechanically compose already-generated candidate site indexes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from webwright.skill_factory.audited_primitive_build import compose_candidate_indexes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("indexes", nargs="+")
    args = parser.parse_args()
    values = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.indexes]
    result = compose_candidate_indexes(
        site=args.site, indexes=values, output=Path(args.output) / args.site / "final_candidate"
    )
    Path(args.output).mkdir(parents=True, exist_ok=True)
    summary_path = Path(args.output) / "summary.json"
    summary = {"status": "candidate", "promoted": False, "sites": {}}
    if summary_path.exists():
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
        if isinstance(existing.get("sites"), dict):
            summary["sites"].update(existing["sites"])
    summary["sites"][args.site] = {
        "site": args.site, "status": "candidate",
        "final_count": len(result["primitives"]),
    }
    summary["sites"] = dict(sorted(summary["sites"].items()))
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
