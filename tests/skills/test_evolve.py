"""Unit test: evolve (growing library, usage-driven). Stubs _refine to stay LLM-free."""
import sys, tempfile
from pathlib import Path
pass
import webwright.skills.update as U
from webwright.skills.library import Library, Skill


def run():
    # stub _refine: deterministically "build/widen" a skill for the group's template
    def fake_refine(group, library):
        from webwright.skills.update import _slug
        sid = _slug(group[0].template)
        library.add(Skill(sid, f"# refined from {len(group)} solves\n",
                          {"template": group[0].template, "provenance": "test-refine"}))
        return [sid]
    U._refine = fake_refine

    with tempfile.TemporaryDirectory() as d:
        lib = Library(d)

        # round 1: template T1 not in lib, skip verdict -> ADD
        t1 = [U.Trace("T1", "code", verdict="skip", correct=True),
              U.Trace("T1", "code", verdict="skip", correct=True)]
        log1 = U.evolve(t1, lib)
        assert log1["added"], f"new template should be added: {log1}"
        assert len(lib.list()) == 1

        # round 2: T1 now exists, all USE success -> library unchanged
        t2 = [U.Trace("T1", "code", used_skill_id="t1", verdict="use", correct=True)]
        log2 = U.evolve(t2, lib)
        assert log2["use"] and not log2["added"] and not log2["adapt_refined"], log2
        assert len(lib.list()) == 1, "pure use must not change library"

        # round 3: T1 exists, an ADAPT happened -> refine back (widen)
        t3 = [U.Trace("T1", "code2", used_skill_id="t1", verdict="adapt", correct=True)]
        log3 = U.evolve(t3, lib)
        assert log3["adapt_refined"], f"adapt should refine back: {log3}"

        # wrong solves are dropped (not fed to refine)
        t4 = [U.Trace("T2", "bad", verdict="skip", correct=False)]
        log4 = U.evolve(t4, lib)
        assert log4["dropped_wrong"] == 1 and not log4["added"], log4

    print("test_evolve OK")


if __name__ == "__main__":
    run()
