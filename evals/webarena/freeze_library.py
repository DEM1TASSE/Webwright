#!/usr/bin/env python3
"""Snapshot or verify the immutable library used by the test arm."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def snapshot(root):
    root = Path(root)
    files = {}
    for path in sorted(x for x in root.rglob("*") if x.is_file()):
        relative = path.relative_to(root).as_posix()
        files[relative] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return {"root": str(root), "files": files}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["snapshot", "verify"])
    parser.add_argument("--library", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    current = snapshot(args.library)
    path = Path(args.manifest)
    if args.command == "snapshot":
        path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"frozen {len(current['files'])} files")
        return 0
    expected = json.loads(path.read_text(encoding="utf-8"))
    if current != expected:
        expected_files, current_files = expected.get("files", {}), current["files"]
        changed = sorted(
            key for key in set(expected_files) | set(current_files)
            if expected_files.get(key) != current_files.get(key)
        )
        print(json.dumps({"valid": False, "changed": changed}, indent=2))
        return 1
    print(json.dumps({"valid": True, "files": len(current["files"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
