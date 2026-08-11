"""Stage definitions shared by the checker CLI and the driver.

Every stage is one terminal-agent episode with the same on-disk contract:

    <workspace>/in/context.json   inputs the driver staged (read-only by convention)
    <workspace>/in/sources/*.py   source workflow code, so the agent can grep/AST it
    <workspace>/out/<artifact>    the single JSON file the agent must produce

The agent validates its own artifact with ``python -m skill_agent.check <stage>`` and is
only allowed to finish once that command exits 0. The validators are imported verbatim
from the scripted pipeline so the agentic output stays comparable to the scripted output.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from webwright.skill_factory.audited_primitive_build import (
    validate_build_proposal,
    validate_consolidation,
    validate_extraction,
    validate_quality_verdicts,
)


def _pool_dict(pool: list[dict] | dict[str, dict]) -> dict[str, dict]:
    if isinstance(pool, dict):
        return pool
    return {str(x["primitive_id"]): x for x in pool}


def _check_extract(context: dict, artifact: dict) -> list[str]:
    return validate_extraction(artifact, workflow=context["workflow"])


def _check_build(context: dict, artifact: dict) -> list[str]:
    _, errors = validate_build_proposal(
        artifact,
        site=context["site"],
        batch=context["batch"],
        pool=_pool_dict(context.get("pool") or []),
        all_workflows={str(k): v for k, v in (context.get("all_workflows") or {}).items()},
        extractions=context.get("extractions") or [],
    )
    return errors


def _check_quality(context: dict, artifact: dict) -> list[str]:
    return validate_quality_verdicts(
        artifact,
        context.get("operations") or [],
        context.get("candidate_attribution") or [],
    )


def _check_consolidate(context: dict, artifact: dict) -> list[str]:
    _, errors, _ = validate_consolidation(
        artifact,
        site=context["site"],
        pool=_pool_dict(context.get("pool") or []),
        workflows={str(k): v for k, v in (context.get("workflows") or {}).items()},
    )
    return errors


@dataclass(frozen=True)
class Stage:
    name: str
    artifact: str
    prompt: str
    check: Callable[[dict, dict], list[str]]
    step_limit: int

    def artifact_path(self, workspace: Path) -> Path:
        return Path(workspace) / "out" / self.artifact

    def context_path(self, workspace: Path) -> Path:
        return Path(workspace) / "in" / "context.json"

    def load_context(self, workspace: Path) -> dict[str, Any]:
        return json.loads(self.context_path(workspace).read_text(encoding="utf-8"))

    def load_artifact(self, workspace: Path) -> dict[str, Any]:
        path = self.artifact_path(workspace)
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist yet")
        return json.loads(path.read_text(encoding="utf-8"))

    def validate(self, workspace: Path) -> tuple[dict, list[str]]:
        """Return (artifact, errors). A missing/unparsable artifact is itself an error."""
        context = self.load_context(workspace)
        try:
            artifact = self.load_artifact(workspace)
        except FileNotFoundError as exc:
            return {}, [f"missing artifact: {exc}"]
        except json.JSONDecodeError as exc:
            return {}, [f"out/{self.artifact} is not valid JSON: {exc}"]
        if not isinstance(artifact, dict):
            return {}, [f"out/{self.artifact} must be a JSON object, got {type(artifact).__name__}"]
        return artifact, list(self.check(context, artifact))


STAGES: dict[str, Stage] = {
    "extract": Stage("extract", "extraction.json", "extract.md", _check_extract, 25),
    "build": Stage("build", "proposal.json", "build.md", _check_build, 40),
    "quality": Stage("quality", "verdicts.json", "quality.md", _check_quality, 25),
    "consolidate": Stage("consolidate", "proposal.json", "consolidate.md", _check_consolidate, 40),
}
