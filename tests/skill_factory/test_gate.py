"""Unit test: admission gate (deterministic, no external)."""
import sys
import json
from pathlib import Path
pass
from webwright.skill_factory.gate import external_gate, gate, load_external_verdicts

ARR = {"type": "array", "items": {"type": "string"}}


def run():
    # self_verify: reject null / empty, admit non-empty
    assert gate(None, method="self_verify").admit is False
    assert gate([], method="self_verify").admit is False
    assert gate("", method="self_verify").admit is False
    assert gate(["Sprite"], method="self_verify").admit is True

    # self_verify: shape must match output_schema
    assert gate(["a", "b"], output_schema=ARR, method="self_verify").admit is True
    assert gate({"x": 1}, output_schema=ARR, method="self_verify").admit is False, "dict != array schema"

    # gold: admit iff equal
    assert gate(["Sprite"], gold=["Sprite"], method="gold").admit is True
    assert gate(["Pepsi"], gold=["Sprite"], method="gold").admit is False

    # auto: gold present -> use gold; absent -> self_verify
    assert gate(["Sprite"], gold=["Sprite"]).admit is True          # auto+gold -> match
    assert gate(["Pepsi"], gold=["Sprite"]).admit is False          # auto+gold -> mismatch -> reject
    assert gate(["anything"]).admit is True                          # auto, no gold -> self_verify pass
    assert gate(None).admit is False                                 # auto, no gold -> self_verify fail

    # self_verify folds in the agent's own final report (free signal, no LLM)
    r = gate(["ok"], method="self_verify", status="NOT_FOUND_ERROR")
    assert not r.admit and "reported NOT_FOUND_ERROR" in r.reason, r
    assert gate(["ok"], method="self_verify", status="SUCCESS").admit
    assert gate(["ok"], method="self_verify").admit, "no status -> unchanged behaviour"
    # gold outranks the self-report path entirely
    assert gate([1], gold=[1], method="auto", status="NOT_FOUND_ERROR").admit

    # imported OM2W JSONL verdicts are strict and fail closed for absent tasks
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "judge.jsonl"
        p.write_text("\n".join(json.dumps(x) for x in [
            {"task_id": "pass", "predicted_label": 1,
             "evaluation_details": {"response": "Status: success"}},
            {"task_id": "fail", "predicted_label": 0},
        ]))
        verdicts = load_external_verdicts(p)
        assert external_gate("pass", verdicts).admit
        assert not external_gate("fail", verdicts).admit
        missing = external_gate("missing", verdicts)
        assert not missing.admit and "no external" in missing.reason

    print("test_gate OK")


# pytest entry point (CI also runs this file as a script)
def test_all():
    run()


if __name__ == "__main__":
    run()
