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
    "You turn a user's one-line description of a web task into a REUSABLE TEMPLATE. "
    "Return STRICT JSON: {\"task\": \"<one sentence with {param} holes>\", "
    "\"params\": [\"<name>\", ...], \"start_url\": \"<best-guess full URL of the site to start on>\"}.\n"
    "The user almost always describes ONE CONCRETE INSTANCE of a task they will repeat with "
    "different values ('the cheapest makeup remover on Amazon' means 'the cheapest {product} on "
    "Amazon'). GENERALIZE: every concrete value they mention — a product, a place, a date, a "
    "name, a count — becomes a {hole}. Do not echo their example values back; the task must "
    "contain holes, not their specifics.\n"
    "Keep genuinely site-fixed things literal (the site itself, the phrasing). Every {hole} in "
    "task MUST appear in params and vice-versa. Ask for the answer in a stable, unambiguous form. "
    "Only if the need truly has nothing that could vary, return params: [].\n"
    "Also judge whether this task's ANSWER DRIFTS. The test is narrow: **run the same task again "
    "tomorrow, changing nothing — is the correct answer still the same string?** Being fetched "
    "live from a busy website does NOT make an answer drift; only the answer moving does.\n"
    "Same site, both cases: 'the earliest nonstop flight from SEA to JFK on 2026-08-15' does NOT "
    "drift — a schedule is published weeks ahead and reads the same tomorrow. 'the cheapest "
    "flight on that route' DOES drift — the fare moves hourly. So: prices, fares, stock, "
    "'today's top seller', anything ranked by a live number → drifts. Schedules, specs, IDs, "
    "counts of past things, published text → does not.\n"
    "Return \"drifts\": true|false, and \"drift_reason\": \"<one clause: what would move, or why "
    "nothing would>\"."
)


def _yaml_skeleton(task: str, params: list[str], start_url: str, rows: int,
                   drifts: bool = False, reason: str = "") -> str:
    cols = ", ".join(f"{p}: \"____\"" for p in params)
    instance_lines = "\n".join(f"  - {{{cols}}}" for _ in range(rows))
    # strict compares the replay against the recorded answer, so it is only fair when the
    # answer holds still. On a drifting answer (a price, stock, a ranking) strict rejects a
    # working skill for doing its job — pick shape up front rather than let the user find out
    # after paying for the solves.
    verify = "shape " if drifts else "strict"
    why = (f"# this answer drifts ({reason}), so replay only checks the shape —\n"
           f"  # strict would reject a working skill for reporting today's truth\n  "
           if drifts else
           f"# this answer should hold still ({reason}), so replay demands the same answer back\n  ")
    return (
        f"# Draft skill spec — fill the ____ values (your ground truth), then: build skill.yaml\n"
        f"# The {{holes}} in `task` are the parameters; each is a column below.\n\n"
        f"task: {task}\n"
        f"start_url: {start_url}    # guessed — check it opens the right page\n\n"
        f"instances:            # give a few real instances (3+ makes a verifiable skill)\n"
        f"{instance_lines}\n\n"
        f"build:                # optional policy — CLI flags override these\n"
        f"  {why}"
        f"verify: {verify}     # strict (reproduce answers) | shape (drifting data) | off\n"
        f"  draws: 2            # independent distillation attempts — a draw can come out brittle\n"
        f"  verify_rounds: 2    # repair rounds within one attempt\n"
        f"  on_fail: reject     # reject = executable or nothing | reference = keep it as a prior\n"
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
        # No holes means the need names ONE task, not a task TYPE — and a skill is only worth
        # building for something you will repeat with different values.
        raise SystemExit(
            f"init: nothing in this need varies, so there is no reusable skill to build:\n"
            f"  {task or '(no task returned)'}\n\n"
            f"Say what CHANGES between runs — name the varying part:\n"
            f"  instead of 'the cheapest makeup remover on Amazon'\n"
            f"  try     'the cheapest <product> on Amazon, for any product'\n\n"
            f"If you really only want this one answer once, you don't need a skill — solve it "
            f"directly (webwright), or use /webwright:craft to get a re-runnable CLI for it.")
    # trust the holes actually in the template over a possibly-mismatched params list
    params = [p for p in params if p in holes] or sorted(holes)
    drifts = bool(data.get("drifts"))
    reason = (data.get("drift_reason") or "").strip().rstrip(".") or (
        "it changes on its own" if drifts else "nothing in it moves on its own")
    out.write_text(_yaml_skeleton(task, params, start_url, rows, drifts, reason), encoding="utf-8")
    print(f"wrote {out}\n\n  task:      {task}\n  params:    {params}\n  start_url: {start_url}\n  verify:    {'shape (this answer drifts)' if drifts else 'strict (this answer should hold still)'}\n\n"
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
