"""Test for feature ①: extract the answer from a webwright run dir.

Plain webwright solves have NO agent_response.json — the answer lives in the trajectory's
exit message (extra.submission / extra.final_response, always a STRING). This tests the
extractor that learn.collect_runs should use as a fallback.

`answer_from_run(dir)` below is the REFERENCE implementation (lift it into collect_runs).
Pure stdlib, no model, no browser. Run:  python 2026-07-21_traj_answer_extraction_test.py
"""
import glob
import json
import tempfile
from pathlib import Path

# test the REAL implementation (needs the webwright venv on the path)
from webwright.skill_factory.learn import answer_from_run


# ---------- fixtures ----------
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
        content = final_response if final_response else "Task completed."
        msgs = [{"role": "assistant", "content": "…"},
                {"role": "exit", "content": content, "extra": extra}]
        (d / "trajectory.json").write_text(json.dumps({"messages": msgs}), encoding="utf-8")
    if agent_response is not None:
        (d / "agent_response.json").write_text(json.dumps(agent_response), encoding="utf-8")
    return str(d)


PLAIN_TASK = {"task": "cheapest flight SEA->DEN ...", "task_id": "t", "start_url": "https://x"}

CASES = []  # (name, run_dir_factory(tmp) -> dir, expected)  expected=None means SKIP

def build_cases(tmp):
    cases = []

    # A) REAL plain trajectory (no agent_response.json) — persisted fixture, else /tmp if present
    fixture = Path(__file__).parent / "data" / "plain_solve_fixture"
    real = [str(fixture)] if (fixture / "trajectory.json").exists() else sorted(glob.glob("/tmp/plain_solve/outputs/plain_solve_*"))
    if real:
        cases.append(("real_plain_structured", real[-1], (["Frontier", "$45"], "SUCCESS")))

    # B) Submitted + prose answer -> keep as string
    cases.append(("submitted_prose",
        make_run(tmp, "b", task=PLAIN_TASK, exit_status="Submitted",
                 final_response="The cheapest flight is Frontier at $45."),
        ("The cheapest flight is Frontier at $45.", "SUCCESS")))

    # C) Submitted + structured string -> parsed
    cases.append(("submitted_structured",
        make_run(tmp, "c", task=PLAIN_TASK, exit_status="Submitted",
                 final_response='["Frontier", "$45"]'),
        (["Frontier", "$45"], "SUCCESS")))

    # D) Submitted but empty final_response -> SKIP
    cases.append(("submitted_empty",
        make_run(tmp, "d", task=PLAIN_TASK, exit_status="Submitted", final_response=""),
        None))

    # E) LimitsExceeded -> SKIP
    cases.append(("limits_exceeded",
        make_run(tmp, "e", task=PLAIN_TASK, exit_status="LimitsExceeded", final_response=None),
        None))

    # F) pipeline agent_response.json present -> use retrieved_data (even if exit differs)
    cases.append(("pipeline_agent_response",
        make_run(tmp, "f", task=PLAIN_TASK, exit_status="Submitted",
                 final_response="ignored prose",
                 agent_response={"retrieved_data": ["United", "$111"]}),
        (["United", "$111"], "SUCCESS")))

    # G) showcase-schema task.json (no "task" key) -> SKIP
    cases.append(("showcase_schema",
        make_run(tmp, "g", task={"task_prompt": "…", "website": "https://x", "short_id": "s"},
                 exit_status="Submitted", final_response='["x"]'),
        None))

    # H) no exit message at all (crashed before finishing) -> SKIP
    cases.append(("no_exit_message",
        make_run(tmp, "h", task=PLAIN_TASK, exit_msg=False),
        None))

    return cases


def main():
    with tempfile.TemporaryDirectory() as tmp:
        cases = build_cases(tmp)
        npass = 0
        for name, run_dir, expected in cases:
            got = answer_from_run(run_dir)
            ok = (got == expected)
            npass += ok
            print(f"  [{'PASS' if ok else 'FAIL'}] {name:26s} got={got!r}"
                  + ("" if ok else f"  expected={expected!r}"))
        print(f"\n{npass}/{len(cases)} cases passed")
        return 0 if npass == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
