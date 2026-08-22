"""Additional tests for the plain-trajectory learn path (features ① collect / ② canonicalize).

Covers, in priority order:
  ② reshape-only: a missing field must become null, never a fabricated value   (gateway)
  ③ canonicalize robustness: garbage / wrong-length LLM output -> safe fallback (offline)
  ④ collect_runs on a MIXED dir: pipeline+plain kept, failed/showcase skipped   (offline)
  ⑦ regression guard: mechanical canonicalize == old infer_schema, unchanged    (offline)

Run (webwright venv; set OPENAI_* to also run the gateway case):
    python 2026-07-21_learn_more_tests.py
"""
import json
import os
import re
import tempfile
from pathlib import Path

import webwright.skill_factory.learn as L
from webwright.skill_factory.learn import canonicalize_answers, collect_runs, infer_schema

npass = ntot = 0
def check(name, cond, extra=""):
    global npass, ntot
    ntot += 1; npass += bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  ' + str(extra)) if extra else ''}")

FLIGHT_TMPL = "Find the cheapest one-way flight from {{origin}} to {{destination}} and return [airline, price]."


def make_run(root, name, *, task=None, exit_status=None, final_response=None,
             agent_response=None, exit_msg=True):
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    if task is not None:
        (d / "task.json").write_text(json.dumps(task), encoding="utf-8")
    if exit_msg:
        extra = {}
        if exit_status is not None:
            extra["exit_status"] = exit_status
        if final_response is not None:
            extra["submission"] = final_response
            extra["final_response"] = final_response
        msgs = [{"role": "exit", "content": final_response or "Task completed.", "extra": extra}]
        (d / "trajectory.json").write_text(json.dumps({"messages": msgs}), encoding="utf-8")
    if agent_response is not None:
        (d / "agent_response.json").write_text(json.dumps(agent_response), encoding="utf-8")
    return d


PLAIN = {"task": "cheapest flight A->B", "task_id": "t", "start_url": "https://x"}

print("── ⑦ regression guard (mechanical canonicalize == infer_schema, unchanged) ──")
for ans in [["Frontier", "$45"], [1, 2, 3], {"a": 1}, [{"x": 1}, {"x": 2}], "prose only"]:
    s, c = canonicalize_answers("t", [ans, ans])   # consistent shape -> mechanical (string pair too)
    if ans == "prose only":
        continue   # two identical strings are NOT structured -> would hit LLM; skip here
    check(f"regress {json.dumps(ans)[:24]}", s == infer_schema(ans) and c == [ans, ans], str(s))

print("── ③ canonicalize robustness: bad LLM output -> safe fallback (offline) ──")
_orig = L.llm_json
try:
    L.llm_json = lambda *a, **k: {"garbage": True}                       # no schema/answers
    s, c = canonicalize_answers("t", ["prose a", "prose b"])
    check("garbage -> no crash + raw kept", c == ["prose a", "prose b"] and isinstance(s, dict))
    check("garbage -> string schema", s == {"type": "string"}, str(s))
    L.llm_json = lambda *a, **k: {"output_schema": {"type": "array"}, "answers": [1]}  # wrong length
    s, c = canonicalize_answers("t", ["prose a", "prose b"])
    check("wrong-length -> raw kept", c == ["prose a", "prose b"], str(c))
finally:
    L.llm_json = _orig

print("── ④ collect_runs on a MIXED dir (pipeline+plain kept, failed/showcase skipped) ──")
with tempfile.TemporaryDirectory() as tmp:
    make_run(tmp, "1_pipeline", task=PLAIN, exit_status="Submitted", final_response="x",
             agent_response={"retrieved_data": ["United", "$111"]})
    make_run(tmp, "2_plain", task=PLAIN, exit_status="Submitted", final_response='["Frontier", "$45"]')
    make_run(tmp, "3_limits", task=PLAIN, exit_status="LimitsExceeded", final_response=None)
    make_run(tmp, "4_showcase", task={"task_prompt": "…", "website": "https://x"},
             exit_status="Submitted", final_response='["x"]')
    (Path(tmp) / "5_bare").mkdir()   # not a run at all
    got = collect_runs(Path(tmp), {"runs": {}})
    ids = sorted(r["task_id"] for r in got)
    answers = {r["dir"].split("/")[-1]: r["answer"] for r in got}
    check("collected exactly pipeline+plain (2)", len(got) == 2, ids)
    check("pipeline answer via retrieved_data", answers.get("1_pipeline") == ["United", "$111"])
    check("plain answer via exit message", answers.get("2_plain") == ["Frontier", "$45"])

print("── ② reshape-only: missing field -> null, never fabricated (gateway) ──")
if not os.environ.get("OPENAI_API_KEY"):
    print("  [SKIP] set OPENAI_API_KEY/OPENAI_ENDPOINT/OPENAI_MODEL to run")
else:
    prose = ["Frontier is the cheapest one-way flight; the price was not shown."]
    schema, coerced = canonicalize_answers(FLIGHT_TMPL, prose)
    blob = json.dumps(coerced[0], ensure_ascii=False)
    check("no fabricated digit (price not invented)", re.search(r"\d", blob) is None, blob)
    check("airline preserved", "frontier" in blob.lower(), blob)

print(f"\n{npass}/{ntot} checks passed")
raise SystemExit(0 if npass == ntot else 1)
