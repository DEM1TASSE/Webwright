#!/usr/bin/env python3
"""Merge independently executed per-site workflow build audit logs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    events = []
    for value in args.input:
        path = Path(value)
        if path.is_file():
            rows = json.loads(path.read_text(encoding="utf-8"))
            for index, row in enumerate(rows):
                row = dict(row)
                row["audit_source"] = str(path.resolve())
                row["audit_source_index"] = index
                events.append(row)
    events.sort(key=lambda row: (
        row.get("site", ""), int(row.get("template_id", -1)),
        row.get("audit_source", ""), row.get("audit_source_index", -1),
    ))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    terminal = {}
    for row in events:
        key = (row.get("site"), int(row.get("template_id", -1)))
        if row.get("status") == "built" or key not in terminal:
            terminal[key] = row
    summary = {
        "templates": len(terminal),
        "built": sum(row.get("status") == "built" for row in terminal.values()),
        "insufficient_gold_sources": sum(
            row.get("status") == "insufficient_gold_sources" for row in terminal.values()
        ),
        "failed": sum(row.get("status") == "failed" for row in terminal.values()),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
