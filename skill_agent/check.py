"""Validator CLI the terminal agent runs against its own artifact.

This is the whole point of the port: in the scripted pipeline the validator errors were
only ever seen by the *next* prompt, so a stage got at most ``max_attempts`` blind retries.
Here the agent runs the identical validator itself, as often as it likes, and reads the
errors as normal command output before deciding what to fix.

    python -m skill_agent.check extract          # validate ./out/extraction.json
    python -m skill_agent.check build --workspace /path/to/ws

Exit code 0 means accepted. Exit code 1 means rejected; the report lists every error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .stages import STAGES


def run(stage_name: str, workspace: Path) -> tuple[int, dict]:
    stage = STAGES[stage_name]
    _, errors = stage.validate(workspace)
    report = {
        "stage": stage_name,
        "artifact": f"out/{stage.artifact}",
        "accepted": not errors,
        "error_count": len(errors),
        "errors": errors,
    }
    return (0 if not errors else 1), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stage", choices=sorted(STAGES))
    parser.add_argument("--workspace", default=".", help="Stage workspace (default: cwd)")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    try:
        code, report = run(args.stage, workspace)
    except FileNotFoundError as exc:
        print(json.dumps({"stage": args.stage, "accepted": False,
                          "errors": [f"cannot read stage input: {exc}"]}, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["accepted"]:
        print(f"\nOK: {args.stage} accepted.")
    else:
        print(f"\nREJECTED: {report['error_count']} error(s). Fix out/{STAGES[args.stage].artifact} "
              f"and run this command again.")
    return code


if __name__ == "__main__":
    sys.exit(main())
