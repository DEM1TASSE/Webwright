"""Unit test: deterministic parts of retrieve/decide (no LLM).
The LLM paths are smoke-tested in test_front.py."""
import sys, tempfile
from pathlib import Path
pass
from webwright.skills.library import Library, Skill
from webwright.skills.retrieve import retrieve, Candidate
from webwright.skills.decide import decide, Decision


def _lib(d):
    lib = Library(d)
    lib.add(Skill("bestsellers", "x", {"template": "Get the top best-selling product in period",
                                        "summary": "magento bestsellers report"}))
    lib.add(Skill("reviews", "x", {"template": "Get reviewers who mention something",
                                   "summary": "product page reviews"}))
    return lib


def run():
    with tempfile.TemporaryDirectory() as d:
        lib = _lib(d)

        # retrieve(method="simple"): keyword overlap, deterministic
        cands = retrieve("top best-selling product", lib, method="simple")
        assert cands, "simple retrieve should find the bestsellers skill"
        assert cands[0].skill.skill_id == "bestsellers", "most-overlapping skill ranked first"

        cands2 = retrieve("zzz nonsense quux", lib, method="simple")
        assert cands2 == [], "no overlap -> no candidates"

        # decide with no candidates -> skip (deterministic, no LLM)
        d0 = decide("anything", [])
        assert isinstance(d0, Decision) and d0.verdict == "skip" and d0.skill_id is None

    print("test_retrieve_decide OK")


if __name__ == "__main__":
    run()
