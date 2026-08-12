"""Where an episode's state lives.

The agent drives the procedure itself, so the commands it runs have to find the same state
the driver set up — without the agent passing paths around. The driver forwards these as
environment variables; every command resolves them here.

    SKILL_AGENT_LIBRARY        <output>/<site> — the persistent library being built
    SKILL_AGENT_BATCH          batch number this episode is responsible for
    SKILL_AGENT_MODEL_CONFIG   model yaml, so `gate` can spawn its judge
    SKILL_AGENT_REPO_ROOT      repo root, so `gate` can build a runner
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ENV_LIBRARY = "SKILL_AGENT_LIBRARY"
ENV_BATCH = "SKILL_AGENT_BATCH"
ENV_MODEL_CONFIG = "SKILL_AGENT_MODEL_CONFIG"
ENV_REPO_ROOT = "SKILL_AGENT_REPO_ROOT"


class MissingState(RuntimeError):
    """Raised with an actionable message rather than a bare KeyError/FileNotFoundError."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingState(f"{name} is not set; this command must run inside a stage workspace")
    return value


def library_dir() -> Path:
    return Path(_require(ENV_LIBRARY))


def batch_number() -> int:
    return int(_require(ENV_BATCH))


def model_config() -> str:
    return _require(ENV_MODEL_CONFIG)


def repo_root() -> Path:
    return Path(_require(ENV_REPO_ROOT))


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pool_path(library: Path | None = None) -> Path:
    """The live primitive pool, carried across batch episodes."""
    return (library or library_dir()) / "pool.json"


def load_pool(library: Path | None = None) -> dict[str, dict]:
    path = pool_path(library)
    if not path.exists():
        return {}
    return {str(x["primitive_id"]): x for x in load(path)}


def save_pool(pool: dict[str, dict], library: Path | None = None) -> None:
    dump(pool_path(library), list(pool.values()))


def load_context(workspace: Path | None = None) -> dict:
    workspace = Path(workspace or ".")
    path = workspace / "in" / "context.json"
    if not path.exists():
        raise MissingState(f"{path} not found; run this from the episode workspace")
    return load(path)


def load_extractions(workspace: Path | None = None, *, batch: list[dict] | None = None) -> list[dict]:
    """Accepted extractions this episode produced, in batch order.

    Build validation needs them in the same order as the batch, and a workflow the agent has
    not extracted yet must surface as a clear gap rather than a silent shift.
    """
    workspace = Path(workspace or ".")
    directory = workspace / "out" / "extractions"
    if batch is None:
        batch = load_context(workspace).get("batch") or []
    found = []
    for workflow in batch:
        path = directory / f"{workflow['id']}.json"
        if path.exists():
            found.append(load(path))
    return found
