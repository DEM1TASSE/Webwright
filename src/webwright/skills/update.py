"""沉淀（间歇）：把通过 gate 的解蒸馏、写回 library，让库从使用中长大。

接口稳定（实现可换）：
    update(traces, library, *, method="grow") -> [被加/更新的 skill_id]

- method="grow"   : 库里还没覆盖这个 template 的，就把这条成功解原样提升为技能（最小形态）。
- method="refine" : 批量提炼——对齐 N 个 gate 过的解 → 参数化(泛化) + 拆出可复用 primitive + 薄任务层
                    → 一个更好的库技能。这是"update 加泛化性 + primitive 复用性"的实现（单次 LLM 批量调用）。
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field

from .library import Library, Skill
from .llm import llm


@dataclass
class Trace:
    template: str
    code: str                       # 这条任务的 final_script（已过 gate = 正确）
    answer: object = None
    meta: dict = field(default_factory=dict)   # params / site / start_url / output_schema ...
    # usage：这条任务是怎么用库的（驱动 update 的信号）
    used_skill_id: str | None = None
    verdict: str | None = None      # use | adapt | skip
    correct: bool = True


def _slug(template: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", template.lower()).strip("_")
    return s[:48] or "skill"


def _extract_code(txt: str) -> str:
    m = re.search(r"```(?:python)?[ \t]*\n", txt)
    if m:
        end = txt.rfind("```")
        if end > m.end():
            return txt[m.end():end]
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
    """批量提炼：对齐 N 个 gate 过的解 → 参数化 + primitive。
    增量：若库里已有同 template 技能，则在【现有技能基础上】改进/加宽（而非从原始解重写）。"""
    if not traces:
        return []
    template = traces[0].template
    schema = traces[0].meta.get("output_schema")
    sid = _slug(template)
    existing = library.get(sid)   # 已有技能？→ 增量演化

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


def _grow(traces: list[Trace], library: Library) -> list[str]:
    existing = {s.meta.get("template") for s in library.list()}
    added = []
    for tr in traces:
        if not tr.template or tr.template in existing:
            continue
        sid = _slug(tr.template)
        meta = {"template": tr.template, "provenance": "distilled", **tr.meta}
        library.add(Skill(skill_id=sid, code=tr.code, meta=meta))
        existing.add(tr.template)
        added.append(sid)
    return added


def evolve(traces: list[Trace], library: Library) -> dict:
    """统一 update：在【已有库】上，按每条轨迹的 usage(use/adapt/skip)决定怎么改库。
    这是"可持续增长的库"的核心——不是每次从零建，而是在 v_{n-1} 上长出 v_n。

    - USE   成功的轨迹：技能够好，不动库（只是复用证据）。
    - ADAPT 成功的轨迹：复用了核心、fix 了末端 → 把这批 fix 后的解【提炼回该 template 的技能】
                        （加宽/更稳）。这就是"fix 沉淀进库"。
    - SKIP / 库没覆盖：该 template 还没有技能 → 用这批解【新增】一个技能。

    只吃 gate 过(correct=True)的轨迹（防污染）。返回一份 changelog。
    """
    good = [t for t in traces if t.correct]
    changelog = {"use": [], "adapt_refined": [], "added": [], "dropped_wrong": len(traces) - len(good)}
    existing_templates = {s.meta.get("template"): s.skill_id for s in library.list()}

    # 按 template 分组（同族解一起提炼/沉淀）
    by_tmpl: dict[str, list[Trace]] = {}
    for t in good:
        by_tmpl.setdefault(t.template, []).append(t)

    for tmpl, group in by_tmpl.items():
        verdicts = {t.verdict for t in group}
        if tmpl not in existing_templates:
            # 库没覆盖 → 新增（用这批解提炼出一个技能）
            sid = _refine(group, library)[0]
            changelog["added"].append(sid)
        elif "adapt" in verdicts:
            # 有 fix 发生 → 把 fix 后的解重新提炼回该技能（加宽/更稳）
            sid = _refine(group, library)[0]   # _refine 用同 slug，覆盖加宽
            changelog["adapt_refined"].append(sid)
        else:
            # 全 use 成功 → 技能够好，不动
            changelog["use"].append(existing_templates[tmpl])
    return changelog


_UPDATERS = {"grow": _grow, "refine": _refine}


def update(traces, library: Library, *, method: str = "grow") -> list[str]:
    return _UPDATERS[method](traces, library)


# ---------- CLI: batch update via a manifest ----------
def traces_from_manifest(manifest: dict) -> list["Trace"]:
    """manifest = {"template": str, "runs": [{"dir","admit","params","answer"?,"verdict"?}, ...]}.
    Reads each run's final_script.py; builds a Trace. correct = the run's gate verdict (admit)."""
    from pathlib import Path
    template = manifest.get("template", "")
    out = []
    for r in manifest.get("runs", []):
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
                         correct=bool(r.get("admit", True)),
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
