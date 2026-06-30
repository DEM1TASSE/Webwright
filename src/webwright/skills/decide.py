"""判断用不用：候选 + 任务 → use / adapt / skip（utility）。

接口稳定（实现可换）：
    decide(task, candidates, *, method="llm") -> Decision
相关 ≠ 有用：retrieve 给"像不像"，decide 给"该不该用、怎么用"。
"""
from __future__ import annotations
from dataclasses import dataclass

from .llm import llm_json


@dataclass
class Decision:
    verdict: str            # "use" | "adapt" | "skip"
    skill_id: str | None
    reason: str


def _decide_llm(task: str, candidates) -> Decision:
    if not candidates:
        return Decision("skip", None, "no candidate skills")
    cat = "\n".join(
        f"- skill_id: {c.skill.skill_id} | template: {c.skill.meta.get('template','')} | "
        f"summary: {c.skill.summary} | params: {c.skill.signature.get('params', [])}"
        for c in candidates
    )
    sys = (
        "Decide whether a library skill is worth using for THIS task. Output STRICT JSON: "
        '{"verdict":"use|adapt|skip","skill_id":"...","reason":"..."}.\n'
        "- use   = the skill fits the task as-is (just different parameter values).\n"
        "- adapt = the skill's expensive core (login / navigation / extraction) is reusable, but the "
        "FINAL step differs; the agent should reuse the front and add/adapt only the last step.\n"
        "- skip  = no candidate is worth it; solve from scratch (skill_id = null).\n"
        "Relevance is not enough — only 'use'/'adapt' if it genuinely saves work."
    )
    user = f"## Task\n{task}\n\n## Candidate skills (most relevant first)\n{cat}"
    out = llm_json(sys, user)
    verdict = out.get("verdict", "skip")
    if verdict not in ("use", "adapt", "skip"):
        verdict = "skip"
    skill_id = out.get("skill_id") if verdict != "skip" else None
    return Decision(verdict=verdict, skill_id=skill_id, reason=out.get("reason", ""))


_DECIDERS = {"llm": _decide_llm}


def decide(task: str, candidates, *, method: str = "llm") -> Decision:
    return _DECIDERS[method](task, candidates)
