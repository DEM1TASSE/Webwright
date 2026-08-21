#!/usr/bin/env python3
"""Intersect one frozen held-out id set with the official execution lanes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_ids(path: str) -> set[int]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path}: expected a JSON list")
    return {int(item) for item in value}


def write_ids(path: Path, values: set[int]) -> None:
    path.write_text(json.dumps(sorted(values), indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heldout", required=True)
    ap.add_argument("--parallel", required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--replay", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    heldout = load_ids(args.heldout)
    parallel = load_ids(args.parallel)
    serial = load_ids(args.serial)
    replay = load_ids(args.replay)
    if parallel & serial:
        raise SystemExit("official parallel and serial lanes overlap")
    missing = heldout - parallel - serial
    if missing:
        raise SystemExit(f"held-out ids missing from execution lanes: {sorted(missing)}")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    parts = {
        "heldout_ids.json": heldout,
        "parallel_ids.json": heldout & parallel,
        "serial_ids.json": heldout & serial,
        "replay_ids.json": heldout & replay,
    }
    for name, values in parts.items():
        write_ids(output / name, values)
    summary = {name.removesuffix("_ids.json"): len(values) for name, values in parts.items()}
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
