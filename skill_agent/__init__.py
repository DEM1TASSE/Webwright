"""Agentic port of the audited primitive build pipeline.

The scripted pipeline in ``webwright.skill_factory.audited_primitive_build`` drives each
stage with a single-shot ``llm_json`` call and feeds validator errors back into the next
prompt. This package keeps the validators byte-identical and replaces the single-shot
calls with terminal-agent episodes: the agent reads the source workflow with bash, writes
its proposal to disk, runs the validator itself, and iterates until the validator exits 0.
"""

__all__ = ["STAGES"]

from .stages import STAGES
