"""Unit test: update 'grow' (deterministic, no LLM)."""
import sys, tempfile
from pathlib import Path
pass
from webwright.skills.library import Library
from webwright.skills.update import update, Trace


def run():
    with tempfile.TemporaryDirectory() as d:
        lib = Library(d)
        assert lib.list() == []

        traces = [
            Trace(template="Get the top-{n} best-selling {entity} in {period}", code="print(1)",
                  answer=["Sprite"], meta={"site": "shopping_admin"}),
            Trace(template="Get the reviewers who mention {x}", code="print(2)", answer=["Bob"]),
        ]
        added = update(traces, lib, method="grow")
        assert len(added) == 2, "two new templates -> two skills added"
        assert len(lib.list()) == 2, "library grew to 2"

        # idempotent: same templates again -> nothing new
        added2 = update(traces, lib, method="grow")
        assert added2 == [], "already-covered templates not re-added"
        assert len(lib.list()) == 2, "library unchanged"

        # the distilled skill carries its code + provenance
        s = lib.get(added[0])
        assert s.code == "print(1)" and s.meta["provenance"] == "distilled"

    print("test_update OK")


if __name__ == "__main__":
    run()
