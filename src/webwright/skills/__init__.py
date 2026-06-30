"""webwright.skills — a memory/skill library module for webwright.

Store solved tasks as reusable, executable code skills; retrieve + judge (use/adapt/skip) at
solve time; admit via a gate; and grow the library incrementally (evolve). Plugs into webwright
as a built-in submodule:
  - solve-time reuse  : the `skill_use` tool (agent invokes it like self_reflection / image_qa)
  - offline growth    : `update.evolve` (run after solves to distill gate-passed solves into skills)

Backend-agnostic: configure_llm(model) wires it to any webwright Model.
"""
from .library import Library, Skill
from .retrieve import retrieve, Candidate
from .decide import decide, Decision
from .gate import gate, GateResult
from .update import evolve, Trace
from .llm import configure_llm
from .prompt import with_skill_hint

__all__ = [
    "Library", "Skill", "retrieve", "Candidate", "decide", "Decision",
    "gate", "GateResult", "evolve", "Trace", "configure_llm", "with_skill_hint",
]
