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

        # skill_use.recommend: a decision pointing OUTSIDE the retrieved candidates (LLM
        # hallucination — even an id that exists in the library) must downgrade to skip
        import webwright.tools.skill_use as T
        orig_retrieve, orig_decide = T.retrieve, T.decide
        try:
            T.retrieve = lambda task, lib: [Candidate(lib.get("bestsellers"), 0.9, "stub")]
            T.decide = lambda task, cands: Decision("use", "reviews", "hallucinated: not a candidate")
            r = T.recommend("top best-selling product", d)
            assert r["verdict"] == "skip" and r["skill_id"] is None, r
            T.decide = lambda task, cands: Decision("use", "bestsellers", "in candidates")
            r2 = T.recommend("top best-selling product", d)
            assert r2["verdict"] == "use" and r2["skill_id"] == "bestsellers", r2
        finally:
            T.retrieve, T.decide = orig_retrieve, orig_decide

    print("test_retrieve_decide OK")


if __name__ == "__main__":
    run()
