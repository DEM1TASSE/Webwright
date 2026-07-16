"""python -m webwright.skill_factory init "<one-line need>" — draft a skill spec you then fill in.

One LLM call turns a natural-language need into a skill.yaml SKELETON: a task template with
{parameter} holes, a *guessed* start_url, and empty instance rows for YOU to fill with real
values. It deliberately does NOT invent the values — those are the ground truth you own, and a
wrong guessed value would quietly train the skill on the wrong answer. Review the file (the
guesses are marked), fill the rows, then run `build skill.yaml`.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .llm import llm_json

_SYS = (
    "You turn a user's one-line description of a repeatable web task into a REUSABLE TEMPLATE. "
    "Return STRICT JSON: {\"task\": \"<one sentence with {param} holes>\", "
    "\"params\": [\"<name>\", ...], \"start_url\": \"<best-guess full URL of the site to start on>\"}.\n"
    "Rules: put a {hole} for every value the user would plausibly vary (places, dates, names, "
    "counts); keep site-fixed things (the site itself, the phrasing) as literal text. Every "
    "{hole} in task MUST appear in params and vice-versa. Ask for the answer in a stable, "
    "unambiguous form. Do NOT put any concrete example values in the task or params — only holes."
)


def _yaml_skeleton(task: str, params: list[str], start_url: str, rows: int) -> str:
    cols = ", ".join(f"{p}: \"____\"" for p in params)
    instance_lines = "\n".join(f"  - {{{cols}}}" for _ in range(rows))
    return (
        f"# Draft skill spec — fill the ____ values (your ground truth), then: build skill.yaml\n"
        f"# The {{holes}} in `task` are the parameters; each is a column below.\n\n"
        f"task: {task}\n"
        f"start_url: {start_url}    # guessed — check it opens the right page\n\n"
        f"instances:            # give a few real instances (3+ makes a verifiable skill)\n"
        f"{instance_lines}\n\n"
        f"build:                # optional policy (defaults shown) — CLI flags override these\n"
        f"  verify: strict      # strict (reproduce answers) | shape (live data) | off\n"
        f"  verify_rounds: 2\n"
        f"  on_fail: reject     # reject | reference\n"
        f"  chunk: 25\n"
    )


def init(need: str, out_path: str, rows: int = 3) -> int:
    out = Path(out_path)
    if out.exists():
        raise SystemExit(f"init: {out} already exists — remove it or pass -o another path.")
    data = llm_json(_SYS, f"Task need: {need}")
    task = (data.get("task") or "").strip()
    params = [str(p) for p in (data.get("params") or [])]
    start_url = (data.get("start_url") or "").strip()
    holes = set(re.findall(r"{(\w+)}", task))
    if not task or not holes:
        raise SystemExit("init: the model did not produce a parameterized task. Try a more "
                         "specific need, e.g. 'find the earliest nonstop flight between two "
                         "cities on a date'.")
    # trust the holes actually in the template over a possibly-mismatched params list
    params = [p for p in params if p in holes] or sorted(holes)
    out.write_text(_yaml_skeleton(task, params, start_url, rows), encoding="utf-8")
    print(f"wrote {out}\n\n  task:      {task}\n  params:    {params}\n  start_url: {start_url}\n\n"
          f"Next: fill the ____ values in {out}, then\n"
          f"  python -m webwright.skill_factory build {out} --library ./library -c your_model.yaml")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m webwright.skill_factory init",
                                description="Draft a skill.yaml skeleton from a one-line need.")
    p.add_argument("need", help="One-line description of the repeatable task you want a skill for.")
    p.add_argument("-o", "--out", default="skill.yaml", help="Where to write the spec.")
    p.add_argument("--rows", type=int, default=3, help="Empty instance rows to leave (default 3).")
    a = p.parse_args(argv)
    return init(a.need, a.out, rows=a.rows)


if __name__ == "__main__":
    sys.exit(main())
