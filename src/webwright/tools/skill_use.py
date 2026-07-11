"""skill_use — solve-time tool: query the skill library for a reusable skill for THIS task.

Like self_reflection / image_qa, the agent invokes this from bash during solving:

    python -m webwright.tools.skill_use --task "Get the latest release version of facebook/react" \
        --library "$WORKSPACE_DIR/../library"

It retrieves the most relevant skill (relevance) and judges utility (use / adapt / skip), then
prints a JSON recommendation telling the agent how to reuse it (and the path to read its source).
The agent decides: reuse as-is (use), reuse the core and change only the last step (adapt), or
solve from scratch (skip). Retrieval/judgement never block solving — on any error it prints skip.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from webwright.skill_lab.library import Library
from webwright.skill_lab.retrieve import retrieve
from webwright.skill_lab.decide import decide


def recommend(task: str, library_root: str) -> dict:
    root = Path(library_root).resolve()
    # A missing/empty library is almost always a wrong path (relative paths resolve inside the
    # agent's workspace). Say so LOUDLY instead of a silent skip — checked before Library(),
    # whose constructor would mkdir the bogus path and hide the mistake.
    if not root.is_dir() or not any((p / "meta.json").exists() for p in root.iterdir() if p.is_dir()):
        return {"verdict": "skip", "skill_id": None,
                "reason": f"skill library MISSING or EMPTY at {root} — check the --library path",
                "warning": f"library empty at {root}"}
    lib = Library(root)
    cands = retrieve(task, lib)
    if not cands:
        return {"verdict": "skip", "skill_id": None, "reason": "library has no relevant skill"}
    d = decide(task, cands)
    # the decision must point at a RETRIEVED candidate — an LLM-hallucinated id (even one that
    # happens to exist in the library) must not be recommended
    if d.verdict != "skip" and d.skill_id not in {c.skill.skill_id for c in cands}:
        return {"verdict": "skip", "skill_id": None,
                "reason": f"decided skill '{d.skill_id}' is not among the retrieved candidates"}
    out = {"verdict": d.verdict, "skill_id": d.skill_id, "reason": d.reason}
    if d.verdict != "skip" and d.skill_id:
        sk = lib.get(d.skill_id)
        if sk:
            out["summary"] = sk.summary
            out["call"] = sk.signature.get("call", "")
            out["source_path"] = str(lib.path(sk.skill_id))
            out["how_to_reuse"] = (
                "USE: copy the source into your final_script and fill THIS task's params; "
                "ADAPT: reuse its login/navigation/extraction core, change ONLY the final step."
            )
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m webwright.tools.skill_use",
        description="Query the skill library for a reusable skill for the current task.",
    )
    p.add_argument("--task", required=True, help="The current task description / intent.")
    p.add_argument("--library", default=os.environ.get("SKILL_LIBRARY_ROOT", "library"),
                   help="Path to the skill library dir (default: $SKILL_LIBRARY_ROOT or ./library).")
    p.add_argument("--output", default="", help="Write JSON to this path instead of stdout.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = recommend(args.task, args.library)
    except Exception as exc:
        # Degrade to skip so solving is never blocked — but say LOUDLY that the library
        # was NOT consulted: a config/auth error here silently disables all reuse otherwise.
        result = {"verdict": "skip", "skill_id": None, "error": str(exc),
                  "reason": "LOOKUP FAILED (library was NOT consulted) — this is an error, "
                            "not a no-match. Check OPENAI_API_KEY and, on a custom gateway, "
                            "OPENAI_ENDPOINT / SKILL_MODEL_ENDPOINT.",
                  }
        print(f"skill_use ERROR: {exc}", file=sys.stderr)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)
    print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
