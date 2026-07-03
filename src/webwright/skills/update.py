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
    "retrieved_data MATCHING output_schema exactly. Output ONLY the python code in one ```python block."
)

_REFINE_INCREMENTAL = (
    "\n\nINCREMENTAL MODE: a CURRENT library skill for this template already exists (shown below). "
    "Do NOT rewrite it from scratch. START from the current skill and IMPROVE it using the NEW solutions: "
    "keep its working primitives and structure, only widen/fix what the new solutions reveal (handle a "
    "param value it missed, make an extraction more robust, fix a bug). Preserve everything that already "
    "works. Output the full improved skill in one ```python block."
)


def _refine(traces: list[Trace], library: Library) -> list[str]:
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
    code = _extract_code(llm(sys_prompt, "\n\n".join(blocks), max_tokens=16000, timeout=400))
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
    library.add(Skill(skill_id=sid, code=code, meta=meta))
    return [sid]


def evolve(traces: list[Trace], library: Library) -> dict:
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
    changelog = {"use": [], "adapt_refined": [], "added": [], "dropped_wrong": len(traces) - len(good)}
    existing_templates = {s.meta.get("template"): s.skill_id for s in library.list()}

    # group by template (same-family solves are distilled/sedimented together)
    by_tmpl: dict[str, list[Trace]] = {}
    for t in good:
        by_tmpl.setdefault(t.template, []).append(t)

    for tmpl, group in by_tmpl.items():
        verdicts = {t.verdict for t in group}
        if tmpl not in existing_templates:
            # not covered -> add (distill a skill from this batch)
            sid = _refine(group, library)[0]
            changelog["added"].append(sid)
        elif "adapt" in verdicts:
            # a fix happened -> refine the fixed solves back into the skill (widen/harden)
            sid = _refine(group, library)[0]   # _refine uses the same slug, overwrites + widens
            changelog["adapt_refined"].append(sid)
        else:
            # all use-success -> skill is good enough, leave it
            changelog["use"].append(existing_templates[tmpl])
    return changelog


# ---------- CLI: batch update via a manifest ----------
def traces_from_manifest(manifest: dict) -> list["Trace"]:
    """manifest = {"template": str, "runs": [{"dir","admit","params","answer"?,"verdict"?}, ...]}.
    Reads each run's final_script.py; builds a Trace. correct = the run's gate verdict (admit).
    "admit" is REQUIRED per run — a missing gate verdict must fail loudly, not silently enter."""
    from pathlib import Path
    template = manifest.get("template", "")
    out = []
    for r in manifest.get("runs", []):
        if "admit" not in r:
            raise KeyError(f"manifest run missing required 'admit' (gate verdict): {r.get('dir', r)}")
        d = Path(r["dir"])
        fs = d / "final_script.py"
        code = fs.read_text(encoding="utf-8") if fs.exists() else ""
        answer = r.get("answer")
        if answer is None and (d / "agent_response.json").exists():
            try:
                answer = json.load(open(d / "agent_response.json")).get("retrieved_data")
            except Exception:
                pass
        out.append(Trace(template=template, code=code, answer=answer,
                         correct=bool(r["admit"]),
                         verdict=r.get("verdict", "skip"),
                         used_skill_id=r.get("used_skill_id"),
                         meta={"params": r.get("params", {}), "site": r.get("site", ""),
                               "start_url": r.get("start_url", ""),
                               "output_schema": r.get("output_schema")}))
    return out


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="python -m webwright.skills.update",
        description="Batch-update the skill library from a manifest of gate-judged solves.")
    p.add_argument("--manifest", required=True, help="JSON: {template, runs:[{dir,admit,params,...}]}")
    p.add_argument("--library", required=True, help="Path to the skill library directory.")
    a = p.parse_args(argv)
    manifest = json.load(open(a.manifest, encoding="utf-8"))
    traces = traces_from_manifest(manifest)
    changelog = evolve(traces, Library(a.library))
    print(json.dumps(changelog, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
