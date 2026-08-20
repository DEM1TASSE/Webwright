#!/usr/bin/env python3
"""Split the official WebArena task set into batches that can safely run together.

Two properties decide how a task may be scheduled:

  does it write?      A task that writes must not run beside tasks that read what it wrote.
  is it replay-safe?  Webwright develops a solution by running its script repeatedly, so a
                      task whose outcome depends on how many times the write happened has to
                      be re-executed exactly once against a freshly reset site.

`program_html` is the wrong proxy for "writes". It both over- and under-counts: 45 navigate
tasks are scored through program_html without writing anything, and 8 tasks write while being
scored by string_match alone. WebArena Verified annotates the intent's `task_type` at
`eval[].expected.task_type`; that annotation is used here for scheduling only. It never reaches
a prompt and never affects scoring, so it does not mix Verified into official results -- but it
is an external judgement, and its intents were rewritten, so treat it as a hint and not truth.

Replay-needed detection is heuristic and deliberately errs toward replaying: a relative amount
in the intent, or a locator that selects by order or counts matches, means duplicate executions
change the verdict.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

RELATIVE = re.compile(
    r"\b(by \d+%|by \$?\d|reduce|increase|decrease|raise|lower|discount|add \d+|bump)\b", re.I)
ORDER_SENSITIVE = re.compile(r"querySelectorAll|\.length|\[0\]|\[1\]|nth-child|first|latest|newest", re.I)


def annotated_type(verified_task: dict) -> str | None:
    for item in verified_task.get("eval") or []:
        expected = item.get("expected") if isinstance(item, dict) else None
        if isinstance(expected, dict) and expected.get("task_type"):
            return expected["task_type"]
    return None


def needs_replay(task: dict) -> bool:
    if RELATIVE.search(task["intent"]):
        return True
    locators = " ".join(str(t.get("locator", "")) for t in (task["eval"].get("program_html") or []))
    return bool(ORDER_SENSITIVE.search(locators))


# WebArena Verified derives task_type from how a task is *scored*, not from what it does. A
# task that creates something but is checked with string_match against the agent's answer --
# "Create an issue asking ...", "Add the following users ... as maintainer" -- is annotated as
# non-mutating and would be scheduled into the parallel lane, where it writes to a deployment
# every other task in that lane is reading. Two such tasks are in the 812; one of them created
# three issues, and three other tasks list open issues in the same project. Nothing was
# affected that run only because of when they happened to start.
WRITE_VERB = re.compile(
    r"^\s*(create|post|add|submit|draft|leave a|reply|invite|assign|fork|upload|delete|remove"
    r"|update|change|set |edit|rename|reduce|increase|cancel|subscribe|unsubscribe|star |vote"
    r"|upvote|downvote|approve|merge|close |reopen)\b", re.I)

# "Create an orders report from ... to ..." renders a filtered view in the Magento admin. It
# reads as a write and is not one, so the verb alone would move five report tasks into the
# serial lane and serialise them for nothing.
READ_ONLY_PHRASE = re.compile(r"^\s*create (an?|the) [\w ]*report\b", re.I)


def writes_despite_annotation(task: dict) -> bool:
    intent = task.get("intent", "")
    return bool(WRITE_VERB.match(intent)) and not READ_ONLY_PHRASE.match(intent)


def write_scope(task: dict) -> str:
    """Coarse identity of what a task writes to. Tasks with different scopes may run together;
    the fallback groups a task alone with everything else whose scope could not be read, which
    serialises more than strictly needed -- the safe direction."""
    target = " ".join(str(t.get("url", "")) for t in (task["eval"].get("program_html") or []))
    if not target or "last" in target or target.startswith("func"):
        target = str(task.get("start_url", ""))
    match = re.search(r"__[A-Z_]+__/([^/?#]+(?:/[^/?#]+)?)", target)
    return f"{task['sites'][0]}:{match.group(1)}" if match else f"{task['sites'][0]}:*"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="official config_files/test.raw.json")
    ap.add_argument("--verified", required=True, help="webarena-verified.json (task_type source)")
    ap.add_argument("--out", required=True, help="directory to write the id lists into")
    args = ap.parse_args()

    official = {t["task_id"]: t for t in json.loads(Path(args.tasks).read_text())}
    verified = {t["task_id"]: t for t in json.loads(Path(args.verified).read_text())}
    missing = sorted(set(official) - set(verified))
    if missing:
        raise SystemExit(f"no task_type annotation for {len(missing)} tasks, e.g. {missing[:5]}")

    parallel, serial = [], []
    for task_id, task in official.items():
        mutates = (annotated_type(verified[task_id]) == "mutate"
                   or writes_despite_annotation(official[task_id]))
        (serial if mutates else parallel).append(task_id)

    groups = collections.defaultdict(list)
    for task_id in serial:
        groups[write_scope(official[task_id])].append(task_id)
    replay = sorted(t for t in serial if needs_replay(official[t]))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "parallel_ids.json").write_text(json.dumps(sorted(parallel)) + "\n")
    (out / "serial_groups.json").write_text(
        json.dumps({k: sorted(v) for k, v in sorted(groups.items())}, indent=1) + "\n")
    (out / "replay_ids.json").write_text(json.dumps(replay) + "\n")

    deepest = max(len(v) for v in groups.values())
    print(f"parallel (retrieve+navigate): {len(parallel)}")
    print(f"serial   (mutate)           : {len(serial)} in {len(groups)} write scopes")
    print(f"  longest scope             : {deepest}  <- critical path if scopes run concurrently")
    print(f"  of which need replay      : {len(replay)}")
    by_site = collections.Counter(official[t]["sites"][0] for t in serial)
    print("  mutate by site            :", dict(by_site.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
