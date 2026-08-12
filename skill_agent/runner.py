"""Thin adapter between the pipeline driver and whatever terminal-agent harness runs an episode.

The driver only ever calls ``run_episode``. Swapping webwright for SWE-agent/mini-swe-agent
means adding one class here; no stage, prompt, validator, or driver code changes.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class EpisodeResult:
    stage: str
    workspace: Path
    exit_status: str
    api_calls: int
    final_response: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_status == "Submitted" and not self.error

    def to_json(self) -> dict:
        return {
            "stage": self.stage,
            "workspace": str(self.workspace),
            "exit_status": self.exit_status,
            "api_calls": self.api_calls,
            "final_response": self.final_response,
            "error": self.error,
        }


def env_spec(name: str, value: object) -> str:
    """Build an `environment.env.X=...` config spec that survives YAML parsing.

    webwright parses a `key=value` spec's value with ``yaml.safe_load``, and the environment's
    ``env`` field is ``dict[str, str]``. Unquoted, a batch number becomes an int and pydantic
    rejects the whole environment config. Quoting keeps every value a string.
    """
    return f"environment.env.{name}={json.dumps(str(value))}"


class AgentRunner(Protocol):
    def run_episode(
        self, *, stage: str, task: str, workspace: Path, step_limit: int, max_output_tokens: int
    ) -> EpisodeResult:
        ...


@dataclass
class WebwrightRunner:
    """Runs an episode with webwright's DefaultAgent on the local_workspace environment.

    ``local_workspace`` is a plain bash sandbox with the cwd pinned to the episode
    workspace, which is all a build stage needs — no browser is involved anywhere in this
    pipeline. ``repo_root`` and ``repo_root/src`` are forwarded on PYTHONPATH so the agent
    can run ``python -m skill_agent.check`` from inside the workspace.
    """

    model_config: str
    repo_root: Path
    agent_config: Path = field(default=None)  # type: ignore[assignment]
    command_timeout_seconds: int = 240
    extra_specs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root).resolve()
        if self.agent_config is None:
            self.agent_config = self.repo_root / "skill_agent" / "configs" / "skill_agent.yaml"
        self.agent_config = Path(self.agent_config).resolve()

    def _config_spec(self, *, step_limit: int, max_output_tokens: int) -> list[str]:
        pythonpath = f"{self.repo_root}:{self.repo_root / 'src'}"
        # Put the driver's own interpreter first so `python` and `python3` inside the
        # workspace are the same one that imports skill_agent and webwright here. Without
        # this the agent silently falls through to whatever /usr/bin/python3 happens to be.
        path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
        return [
            str(self.agent_config),
            self.model_config,
            f"agent.step_limit={step_limit}",
            f"model.max_output_tokens={max_output_tokens}",
            f"environment.command_timeout_seconds={self.command_timeout_seconds}",
            env_spec("PYTHONPATH", pythonpath),
            env_spec("PATH", path),
            *self.extra_specs,
        ]

    def run_episode(
        self, *, stage: str, task: str, workspace: Path, step_limit: int, max_output_tokens: int
    ) -> EpisodeResult:
        from webwright.run.cli import run_one

        workspace = Path(workspace).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        error = ""
        try:
            result = run_one(
                task=task,
                task_id=stage,
                config_spec=self._config_spec(
                    step_limit=step_limit, max_output_tokens=max_output_tokens
                ),
                resolved_output_dir=workspace,
            )
        except Exception as exc:  # a crashed episode is a stage failure, not a pipeline crash
            result, error = {}, f"{type(exc).__name__}: {exc}"

        api_calls = 0
        trajectory = workspace / "trajectory.json"
        if trajectory.is_file():
            try:
                api_calls = int(json.loads(trajectory.read_text(encoding="utf-8"))
                                .get("info", {}).get("api_calls", 0))
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                api_calls = 0
        return EpisodeResult(
            stage=stage,
            workspace=workspace,
            exit_status=str(result.get("exit_status", "") or ("Error" if error else "")),
            api_calls=api_calls,
            final_response=str(result.get("final_response", "") or ""),
            error=error,
        )
