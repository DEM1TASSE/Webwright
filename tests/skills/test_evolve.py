"""Unit test: evolve (growing library, usage-driven). Stubs _refine to stay LLM-free."""
import sys, tempfile
from pathlib import Path
pass
import webwright.skills.update as U
from webwright.skills.library import Library, Skill


def run():
    # stub _refine: deterministically "build/widen" a skill for the group's template
    def fake_refine(group, library, verify="off"):
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

    # manifest: a run missing the gate verdict must fail loudly, never default to admitted
    try:
        U.traces_from_manifest({"template": "T", "runs": [{"dir": "/nonexistent"}]})
        raise AssertionError("missing 'admit' must raise")
    except KeyError:
        pass
    # ... and a hand-written string "false" (truthy!) must be rejected, not admitted
    try:
        U.traces_from_manifest({"template": "T", "runs": [{"dir": "/x", "admit": "false"}]})
        raise AssertionError("non-bool 'admit' must raise")
    except TypeError:
        pass

    # slug: two long templates sharing a 48-char prefix must NOT collide on one skill id
    long_a = "get the value of " + "x" * 60 + " variant one"
    long_b = "get the value of " + "x" * 60 + " variant two"
    assert U._slug(long_a) != U._slug(long_b), "truncated slugs must be disambiguated"
    assert U._slug(long_a) == U._slug(long_a), "slug must stay deterministic"
    assert U._slug("Get the top-n best-selling entity") == "get_the_top_n_best_selling_entity", \
        "short templates keep the plain readable slug"

    # ---- replay verification (real _refine + _replay, only the LLM is faked) ----
    import importlib
    importlib.reload(U)   # drop the fake_refine stub
    import json as _json

    BAD = 'import json\njson.dump({"retrieved_data": [7]}, open("agent_response.json", "w"))\n'
    GOOD = 'import json\njson.dump({"retrieved_data": [42]}, open("agent_response.json", "w"))\n'
    CRASH = 'raise RuntimeError("distillation bug")\n'

    def mktrace():
        return U.Trace("verify template", "solver code", answer=[42], verdict="skip", correct=True,
                       meta={"params": {"k": "v"}, "output_schema": {"type": "array", "items": {"type": "number"}}})

    with tempfile.TemporaryDirectory() as d:
        lib = Library(d)
        # strict: first attempt wrong -> repair returns good -> ADDED with the repaired code
        replies = iter([BAD, GOOD])
        U.llm = lambda *a, **k: next(replies)
        log = U.evolve([mktrace()], lib, verify="strict")
        assert log["added"] and not log["rejected"], log
        assert "[42]" in lib.list()[0].code, "repaired code must be what landed"

    with tempfile.TemporaryDirectory() as d:
        lib = Library(d)
        # strict: wrong twice -> REJECTED, library stays empty
        replies = iter([BAD, BAD])
        U.llm = lambda *a, **k: next(replies)
        log = U.evolve([mktrace()], lib, verify="strict")
        assert log["rejected"] and not log["added"], log
        assert lib.list() == [], "rejected skill must not land"

    with tempfile.TemporaryDirectory() as d:
        lib = Library(d)
        # shape: a non-empty, schema-shaped answer passes even if values drifted (live data)
        replies = iter([BAD])
        U.llm = lambda *a, **k: next(replies)
        log = U.evolve([mktrace()], lib, verify="shape")
        assert log["added"], f"shape mode must tolerate value drift: {log}"

    with tempfile.TemporaryDirectory() as d:
        lib = Library(d)
        # shape: a CRASHING skill is caught even in the tolerant mode
        replies = iter([CRASH, CRASH])
        U.llm = lambda *a, **k: next(replies)
        log = U.evolve([mktrace()], lib, verify="shape")
        assert log["rejected"], f"crash must be caught: {log}"

    # update CLI smoke: -m webwright.skills.update must not NameError on Path (regression)
    with tempfile.TemporaryDirectory() as d:
        mf = Path(d) / "m.json"
        mf.write_text(_json.dumps({"template": "T", "runs": []}))
        assert U.main(["--manifest", str(mf), "--library", str(Path(d) / "lib")]) == 0

    print("test_evolve OK")


# pytest entry point (CI also runs this file as a script)
def test_all():
    run()


if __name__ == "__main__":
    run()
