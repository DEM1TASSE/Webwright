"""Agentic port of the audited primitive build pipeline.

The scripted pipeline in ``webwright.skill_factory.audited_primitive_build`` drives each step
with a single-shot ``llm_json`` call and feeds validator errors into the next prompt. Here a
terminal agent owns the procedure: it reads the source workflows with bash, writes its
artifacts to disk, and runs ``python -m skill_agent.verify`` until the work is accepted.

The validators are imported unchanged, so an agentic library and a scripted library are
directly diffable.
"""
