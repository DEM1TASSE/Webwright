#!/usr/bin/env python3
"""Split WebArena-Verified tasks into retrieve / navigate / mutate, and rate how
badly each mutate template breaks when its write is executed more than once.

Why this matters: Webwright re-runs `final_script.py` 2-5 times per task
(observed on every task we ran). A write that is not idempotent therefore lands
more than once, and the site ends up in a state the task never asked for.

Usage: classify_mutate_tasks.py <webarena-verified.json> [--list]
"""
import json
import re
import sys
from collections import Counter, defaultdict

# POST to these is a read in disguise (GraphQL queries, search, autocomplete)
READ_ENDPOINT = re.compile(r"/api/graphql|/search|/autocomplete|/refs\?|/api/v4/projects\?")

# Hand-labelled from reading all 75 mutate templates. Anything not listed is
# idempotent, converging ("delete all X"), or purely additive.
REPEAT_RISK = {
    "unique-name-create": {
        "templates": [292, 332, 352, 600, 2100, 84, 87, 88, 7, 256, 258],
        "on_repeat": "second attempt errors (409 / name taken); end state still correct",
        "severity": "noisy",
    },
    "duplicate-add": {
        "templates": [145, 186, 189, 196, 194, 252, 284, 172, 216, 156, 293, 294, 351],
        "on_repeat": "duplicate row, or a no-op the agent reads as failure",
        "severity": "noisy",
    },
    "relative-change": {
        "templates": [247, 742, 27],
        "on_repeat": "ACCUMULATES silently: 'reduce by $5' twice reduces by $10",
        "severity": "corrupting",
    },
    "one-shot-transition": {
        "templates": [257, 335],
        "on_repeat": "precondition consumed; the control disappears and the agent stalls",
        "severity": "stalling",
    },
}


def kind(task):
    """retrieve | navigate | mutate"""
    names = {e.get("evaluator") for e in task.get("eval", [])}
    if names == {"AgentResponseEvaluator"}:
        return "retrieve"
    for e in task.get("eval", []):
        if e.get("evaluator") != "NetworkEventEvaluator":
            continue
        ex = e.get("expected", {})
        if ex.get("http_method") in ("POST", "PUT", "PATCH", "DELETE"):
            urls = ex.get("url", "")
            urls = urls if isinstance(urls, list) else [urls]
            if any(not READ_ENDPOINT.search(u) for u in urls):
                return "mutate"
    return "navigate"


def repeat_risk(template_id):
    for label, spec in REPEAT_RISK.items():
        if template_id in spec["templates"]:
            return label
    return "safe"


def main(dataset_path, *flags):
    tasks = json.loads(open(dataset_path, encoding="utf-8").read())
    kinds = Counter()
    mutate_by_risk = defaultdict(list)
    for t in tasks:
        k = kind(t)
        kinds[k] += 1
        if k == "mutate":
            mutate_by_risk[repeat_risk(t["intent_template_id"])].append(t)

    print(f"{len(tasks)} tasks: " + ", ".join(f"{k}={v}" for k, v in kinds.most_common()))
    print()
    total = sum(len(v) for v in mutate_by_risk.values())
    print(f"{'repeat risk':22s}{'templates':>10}{'tasks':>7}  effect when the write runs twice")
    for label in list(REPEAT_RISK) + ["safe"]:
        rows = mutate_by_risk.get(label, [])
        if not rows:
            continue
        tpl = len({r["intent_template_id"] for r in rows})
        note = REPEAT_RISK.get(label, {}).get("on_repeat", "harmless")
        print(f"{label:22s}{tpl:>10}{len(rows):>7}  {note}")
    unsafe = sum(len(v) for k, v in mutate_by_risk.items() if k != "safe")
    print(f"\nnot idempotent: {unsafe}/{total} mutate tasks ({unsafe / total:.0%})")
    corrupting = mutate_by_risk.get("relative-change", [])
    print(f"silently corrupting (exclude, or reset between executions): "
          f"{len(corrupting)} tasks in templates {sorted(REPEAT_RISK['relative-change']['templates'])}")

    if "--list" in flags:
        for label, rows in mutate_by_risk.items():
            if label == "safe":
                continue
            print(f"\n## {label}")
            for r in rows:
                print(f"  [{r['task_id']:4d}] tpl{r['intent_template_id']:<5d} {r['intent'][:80]}")


if __name__ == "__main__":
    main(*sys.argv[1:])
