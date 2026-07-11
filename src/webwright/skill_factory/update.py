"""Sediment (intermittent): distill gate-passed solves back into the library so it grows from use.

Stable interface (swappable implementation):
    update(traces, library, *, method="grow") -> [added/updated skill_ids]

- method="grow"   : if the library does not yet cover this template, promote the successful solve
                    as-is into a skill (minimal form).
- method="refine" : batch distillation — align N gate-passed solves -> parameterize (generalize) +
                    factor out reusable primitives + a thin task layer -> one better library skill.
                    This is where update adds generalization + primitive reusability (one batched LLM call).
"""
from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .library import Library, Skill
from .llm import llm


@dataclass
class Trace:
    template: str
    code: str                       # this task's final_script (already gate-passed = correct)
    answer: object = None
    meta: dict = field(default_factory=dict)   # params / site / start_url / output_schema ...
    # usage: how this task used the library (the signal that drives update)
    used_skill_id: str | None = None
    verdict: str | None = None      # use | adapt | skip
    correct: bool = True


def _slug(template: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", template.lower()).strip("_")
    if not s:
        return "skill"
    if len(s) <= 48:
        return s
    # truncation could collide two templates that share a long prefix -> disambiguate with a hash
    return f"{s[:40]}_{hashlib.md5(template.encode()).hexdigest()[:7]}"


def _extract_code(txt: str) -> str:
    m = re.search(r"```(?:python)?[ \t]*\n", txt)
    if m:
        end = txt.rfind("```")
        if end > m.end():
            return txt[m.end():end]
        return txt[m.end():]   # opening fence but no close (e.g. truncated) -> strip the fence anyway
    return txt


def _norm(v):
    """Scalar-normalize for replay comparison: 5 == "5" (type jitter between a solve's
    string answer and a skill's numeric one is not a logic error; WebArena's own
    evaluator normalizes the same way)."""
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in sorted(v.items())}
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    return v


def _replay(code: str, traces: list["Trace"], strict: bool = False) -> list[str]:
    """Run the candidate skill on each source trace's OWN taskspec (no model in the loop).
    PASS = exact answer match; in non-strict mode a non-empty, schema-shaped answer also
    passes (live sites drift between solve time and replay time — prices, listings).
    Catches what distillation can break: crashes, timeouts, empty/misshapen output."""
    import os
    import subprocess
    import sys
    import tempfile
    from .gate import gate
    fails = []
    for i, tr in enumerate(traces):
        if tr.answer is None:
            continue
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "skill.py").write_text(code, encoding="utf-8")
            (tdp / "taskspec.json").write_text(json.dumps(
                {"params": tr.meta.get("params", {}), "start_url": tr.meta.get("start_url", ""),
                 "credentials": tr.meta.get("credentials"),
                 "output_schema": tr.meta.get("output_schema")}, ensure_ascii=False),
                encoding="utf-8")
            try:
                subprocess.run([sys.executable, "skill.py", "taskspec.json"], cwd=td,
                               env={**os.environ, "WORKSPACE_DIR": td},
                               capture_output=True, text=True, timeout=240)
            except subprocess.TimeoutExpired:
                fails.append(f"instance {i} (params={json.dumps(tr.meta.get('params'), ensure_ascii=False)}): TIMEOUT")
                continue
            got = None
            arp = tdp / "agent_response.json"
            if arp.exists():
                try:
                    got = json.loads(arp.read_text(encoding="utf-8")).get("retrieved_data")
                except Exception:
                    pass
            if _norm(got) == _norm(tr.answer):
                continue
            if not strict and gate(got, output_schema=tr.meta.get("output_schema"),
                                   method="self_verify").admit:
                continue   # tolerated: live-data drift (right shape, non-empty)
            fails.append(f"instance {i} (params={json.dumps(tr.meta.get('params'), ensure_ascii=False)}): "
                         f"replay returned {json.dumps(got, ensure_ascii=False)[:120]}, "
                         f"the solve's answer was {json.dumps(tr.answer, ensure_ascii=False)[:120]}")
    return fails


def _load_examples(library: Library, sid: str) -> list:
    f = library.path(sid).parent / "replays.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    except Exception:
        return []


def _save_examples(library: Library, sid: str, traces: list["Trace"], old: list) -> None:
    """Persist (params, start_url, output_schema, answer) per admitted solve so future
    incremental refines can REGRESSION-replay old coverage. Credentials are never stored
    (the library may be shared/committed); replay borrows them from the incoming batch."""
    ex = old + [{"params": t.meta.get("params", {}), "start_url": t.meta.get("start_url", ""),
                 "output_schema": t.meta.get("output_schema"), "answer": t.answer}
                for t in traces if t.answer is not None]
    (library.path(sid).parent / "replays.json").write_text(
        json.dumps(ex[-12:], ensure_ascii=False, indent=1), encoding="utf-8")


_REFINE_SYS = (
    "You are given N working Python solutions that EACH solve one concrete instance of the SAME web-task "
    "template (they already passed a correctness gate). Distill them into ONE better library skill.\n"
    "Do TWO things:\n"
    "1) GENERALIZE: align the N solutions; the parts that are IDENTICAL across them are the reusable "
    "skeleton; the parts that DIFFER are parameters. Expose the differing values as function "
    "arguments / taskspec params — do NOT hardcode any instance's specific values. Make extraction "
    "robust (paginate/until-done, self-verify against any declared total).\n"
    "2) DECOMPOSE INTO REUSABLE PRIMITIVES: factor the expensive, reusable core into clearly-named "
    "primitive functions (e.g. login(), open_report(period), extract_rows()), and keep a THIN task "
    "layer on top that calls them. This lets future tasks reuse the primitives even if the final step "
    "differs.\n"
    "Interface (fixed): the skill reads taskspec.json from sys.argv[1] "
    "(taskspec = {params, start_url, credentials, output_schema}) and writes agent_response.json with "
    "retrieved_data MATCHING output_schema exactly. ALL artifacts (answer, logs, screenshots) must go "
    "under the WORKSPACE_DIR env var (default: the current working directory) — never next to "
    "__file__: the skill file lives in a shared library. "
    "Output ONLY the python code in one ```python block."
)

_REFINE_INCREMENTAL = (
    "\n\nINCREMENTAL MODE: a CURRENT library skill for this template already exists (shown below). "
    "Do NOT rewrite it from scratch. START from the current skill and IMPROVE it using the NEW solutions: "
    "keep its working primitives and structure, only widen/fix what the new solutions reveal (handle a "
    "param value it missed, make an extraction more robust, fix a bug). Preserve everything that already "
    "works. Output the full improved skill in one ```python block."
)


def _refine(traces: list[Trace], library: Library, verify: str = "off",
            rounds: int = 2, on_fail: str = "reject") -> list[str]:
    """Batch distillation: align N gate-passed solves -> parameterize + primitives.
    Incremental: if a skill for the same template already exists, improve/widen it on top of the
    existing skill (rather than rewriting from the raw solves)."""
    if not traces:
        return []
    template = traces[0].template
    schema = traces[0].meta.get("output_schema")
    sid = _slug(template)
    existing = library.get(sid)   # skill already exists? -> incremental evolution

    blocks = [f"## Template\n{template}\n\n## Required output_schema for retrieved_data\n{json.dumps(schema)}\n"]
    if existing and existing.code:
        blocks.append(f"## CURRENT library skill (improve THIS, do not rewrite)\n```python\n{existing.code}\n```")
    label = "NEW solutions" if existing else "Solutions"
    for i, tr in enumerate(traces):
        blocks.append(
            f"## {label} {i} (params={json.dumps(tr.meta.get('params'), ensure_ascii=False)}, "
            f"answer={json.dumps(tr.answer, ensure_ascii=False)[:120]})\n```python\n{tr.code}\n```"
        )
    sys_prompt = _REFINE_SYS + (_REFINE_INCREMENTAL if existing else "")
    user_msg = "\n\n".join(blocks)
    code = _extract_code(llm(sys_prompt, user_msg, max_tokens=16000))
    verified = None
    if verify != "off":   # replay the candidate on its own training taskspecs before it may land
        replay_set = list(traces)
        if existing:
            old_ex = _load_examples(library, sid)
            if old_ex:
                creds = traces[0].meta.get("credentials")   # same template family, same site
                replay_set += [Trace(template=template, code="", answer=e.get("answer"),
                                     meta={"params": e.get("params", {}),
                                           "start_url": e.get("start_url", ""),
                                           "credentials": creds,
                                           "output_schema": e.get("output_schema")})
                               for e in old_ex]
            elif existing.meta.get("verified"):
                # a verified skill with no stored regression examples must not be touched:
                # we could not prove the refine keeps its old coverage
                print(f"  ✗ {sid}: existing VERIFIED skill has no replays.json — refine skipped "
                      f"(old coverage can't be regression-checked); old skill kept")
                return []
        verified, fails = False, []
        for attempt in range(1, max(rounds, 1) + 1):
            fails = _replay(code, replay_set, strict=(verify == "strict"))
            if not fails:
                verified = True
                break
            if attempt <= max(rounds, 1) - 1:   # feedback rounds remaining
                feedback = ("\n\n## Replay failures of your previous attempt (fix the GENERAL "
                            "logic, do NOT hardcode answers)\n" + "\n".join(fails) +
                            "\n\n## Your previous attempt\n```python\n" + code + "\n```")
                code = _extract_code(llm(sys_prompt, user_msg + feedback, max_tokens=16000))
        if not verified:
            # NEVER overwrite an existing (possibly verified) skill with an unverified one
            if on_fail == "reference" and not existing:
                print(f"  ! {sid}: replay verification failed after {rounds} round(s) — landing "
                      f"as grade=reference (a readable prior for the agent; standalone NOT trusted)")
            else:
                print(f"  ✗ {sid}: replay verification failed after {rounds} round(s) — NOT written:")
                for f in fails:
                    print(f"      {f}")
                if verify == "strict":
                    print("      (answers that legitimately change between solve and replay — "
                          "prices, live listings — need --verify shape)")
                return []
    n_prev = (existing.meta.get("n_solves", 0) if existing else 0)
    meta = {
        "template": template,
        "provenance": "update-refined-incremental" if existing else "update-refined",
        "site": traces[0].meta.get("site", ""),
        "summary": f"Refined from {n_prev + len(traces)} gate-passed solves; parameterized + primitives.",
        "signature": {"params": list((traces[0].meta.get("params") or {}).keys()),
                      "call": "python skill.py taskspec.json"},
        "output_schema": schema,
        "n_solves": n_prev + len(traces),
        "revisions": (existing.meta.get("revisions", 1) + 1) if existing else 1,
    }
    if verified is not None:
        meta["verified"] = verified
        meta["grade"] = "executable" if verified else "reference"
    library.add(Skill(skill_id=sid, code=code, meta=meta))
    if verify != "off":
        _save_examples(library, sid, traces, _load_examples(library, sid))
    return [sid]


def evolve(traces: list[Trace], library: Library, verify: str = "off",
           rounds: int = 2, on_fail: str = "reject") -> dict:
    """Unified update: evolve the EXISTING library, deciding per trace's usage (use/adapt/skip) how
    to change it. This is the core of a continuously-growing library — not rebuilt from scratch each
    time, but grown from v_{n-1} into v_n.

    - USE   (successful)        : the skill is good enough, leave it untouched (just reuse evidence).
    - ADAPT (successful)        : core reused, last step fixed -> refine this batch's fixed solves
                                  back into the template's skill (widen/harden). This is how a fix
                                  sediments into the library.
    - SKIP / not yet covered    : the template has no skill yet -> add one from this batch.

    Only consumes gate-passed (correct=True) traces (pollution protection). Returns a changelog.
    """
    good = [t for t in traces if t.correct]
    changelog = {"use": [], "adapt_refined": [], "added": [], "reference": [], "rejected": [],
                 "dropped_wrong": len(traces) - len(good)}
    existing_templates = {s.meta.get("template"): s.skill_id for s in library.list()}

    # group by template (same-family solves are distilled/sedimented together)
    by_tmpl: dict[str, list[Trace]] = {}
    for t in good:
        by_tmpl.setdefault(t.template, []).append(t)

    for tmpl, group in by_tmpl.items():
        verdicts = {t.verdict for t in group}
        if tmpl not in existing_templates:
            # not covered -> add (distill a skill from this batch)
            added = _refine(group, library, verify=verify, rounds=rounds, on_fail=on_fail)
            key = "added" if added else "rejected"
            if added and library.get(added[0]) and library.get(added[0]).meta.get("grade") == "reference":
                key = "reference"
            changelog.setdefault(key, []).append(added[0] if added else _slug(tmpl))
        elif "adapt" in verdicts:
            # a fix happened -> refine the fixed solves back into the skill (widen/harden)
            added = _refine(group, library, verify=verify, rounds=rounds, on_fail=on_fail)
            changelog["adapt_refined" if added else "rejected"].append(added[0] if added else _slug(tmpl))
        else:
            # all use-success -> skill is good enough, leave it
            changelog["use"].append(existing_templates[tmpl])
    return changelog


# ---------- CLI: batch update via a manifest ----------
def traces_from_manifest(manifest: dict) -> list["Trace"]:
    """manifest = {"template": str, "runs": [{"dir","admit","params","answer"?,"verdict"?}, ...]}.
    Reads each run's final_script.py; builds a Trace. correct = the run's gate verdict (admit).
    "admit" is REQUIRED per run — a missing gate verdict must fail loudly, not silently enter."""
    template = manifest.get("template", "")
    out = []
    for r in manifest.get("runs", []):
        if "admit" not in r:
            raise KeyError(f"manifest run missing required 'admit' (gate verdict): {r.get('dir', r)}")
        if not isinstance(r["admit"], bool):
            # a hand-written manifest with "admit": "false" would otherwise be truthy -> admitted
            raise TypeError(f"manifest 'admit' must be a JSON boolean, "
                            f"got {type(r['admit']).__name__} {r['admit']!r}: {r.get('dir', r)}")
        d = Path(r["dir"])
        fs = d / "final_script.py"
        code = fs.read_text(encoding="utf-8") if fs.exists() else ""
        answer = r.get("answer")
        if answer is None and (d / "agent_response.json").exists():
            try:
                answer = json.loads((d / "agent_response.json").read_text(encoding="utf-8")).get("retrieved_data")
            except Exception:
                pass
        out.append(Trace(template=template, code=code, answer=answer,
                         correct=r["admit"],
                         verdict=r.get("verdict", "skip"),
                         used_skill_id=r.get("used_skill_id"),
                         meta={"params": r.get("params", {}), "site": r.get("site", ""),
                               "start_url": r.get("start_url", ""),
                               "credentials": r.get("credentials"),
                               "output_schema": r.get("output_schema")}))
    return out


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="python -m webwright.skill_factory.update",
        description="Batch-update the skill library from a manifest of gate-judged solves.")
    p.add_argument("--manifest", required=True, help="JSON: {template, runs:[{dir,admit,params,...}]}")
    p.add_argument("--library", required=True, help="Path to the skill library directory.")
    p.add_argument("--verify", default="off", choices=["off", "shape", "strict"],
                   help="Replay each new skill on its own training taskspecs before it enters "
                        "the library. shape: exact match OR well-formed non-empty (live data); "
                        "strict: exact match only. Needs the sites reachable from here.")
    p.add_argument("--verify-rounds", type=int, default=2,
                   help="Total build attempts (first + repairs) before giving up. Default 2.")
    p.add_argument("--on-fail", default="reject", choices=["reject", "reference"],
                   help="Failed verification: reject (default) or land as grade=reference — "
                        "readable prior for the agent, standalone NOT trusted. Never overwrites "
                        "an existing skill.")
    a = p.parse_args(argv)
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    traces = traces_from_manifest(manifest)
    changelog = evolve(traces, Library(a.library), verify=a.verify,
                       rounds=a.verify_rounds, on_fail=a.on_fail)
    print(json.dumps(changelog, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
