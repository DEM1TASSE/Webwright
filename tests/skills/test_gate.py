"""Unit test: admission gate (deterministic, no external)."""
import sys
from pathlib import Path
pass
from webwright.skills.gate import gate

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

    print("test_gate OK")


# pytest entry point (CI also runs this file as a script)
def test_all():
    run()


if __name__ == "__main__":
    run()
