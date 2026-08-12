"""Drive the whole procedure with a scripted agent instead of a model.

The fake agent does what a real one does — writes its artifacts, then runs `verify` — using the
artifacts the *scripted* pipeline's LLM calls actually produced for Map. So this exercises the
real command surface and the driver's commit path end to end, and asserts the agent-driven
pipeline still reproduces the scripted library's package byte-for-byte.

If it fails, the redesign changed pipeline semantics, not just who is in charge.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from skill_agent import build as build_mod
from skill_agent import context as ctx
from skill_agent import verify as verify_mod
from skill_agent.runner import EpisodeResult

FIXTURE = Path(__file__).parent / "fixtures" / "replay_map"
WORKFLOWS = Path(__file__).parents[2] / "skill_agent" / "inputs" / "workflows" / "map.json"
REPO_ROOT = Path(__file__).parents[2]


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class ReplayJudge:
    """Stands in for the fresh judge episodes that `verify` spawns.

    There are two: a completeness reviewer over the extractions, and a boundary judge over the
    proposal. Each gets its own episode with an empty context.
    """

    calls: list[str] = []

    def __init__(self, **_):
        pass

    def run_episode(self, *, stage, task, workspace, step_limit, max_output_tokens):
        ReplayJudge.calls.append(stage)
        workspace = Path(workspace)
        if stage == "extraction_review":
            extractions = ctx.load_context(workspace).get("extractions") or []
            ctx.dump(workspace / "out" / "extraction_review.json", {"reviews": [
                {"workflow_id": (x.get("candidates") or [{}])[0].get("candidate_id", "").split("::")[0],
                 "verdict": "COMPLETE", "missed": [], "reason": "read the source"}
                for x in extractions]})
        else:
            ctx.dump(workspace / "out" / "verdicts.json",
                     _load(FIXTURE / "quality" / "batch_000.json"))
        return EpisodeResult(stage=stage, workspace=workspace, exit_status="Submitted",
                             api_calls=1, final_response="replayed judge")


class ScriptedAgent:
    """Replays recorded artifacts, then verifies, exactly as the procedure asks."""

    def __init__(self, library: Path, number: int, log: list[str]):
        self.library, self.number, self.log = Path(library), number, log

    def run_episode(self, *, stage, task, workspace, step_limit, max_output_tokens):
        os.environ[ctx.ENV_LIBRARY] = str(self.library)
        os.environ[ctx.ENV_BATCH] = str(self.number)
        os.environ[ctx.ENV_REPO_ROOT] = str(REPO_ROOT)
        os.environ[ctx.ENV_MODEL_CONFIG] = "unused-in-tests.yaml"
        workspace = Path(workspace)
        (self._batch if stage == "batch" else self._site)(workspace)
        code, _, errors, _ = verify_mod.run(workspace)
        self.log.append(f"{stage}: verify -> {'ready' if code == 0 else errors}")
        return EpisodeResult(stage=stage, workspace=workspace, exit_status="Submitted",
                             api_calls=1, final_response="replayed")

    def _write_ops(self, ws: Path, operations: list[dict], *, with_code: bool) -> None:
        for index, operation in enumerate(operations):
            operation = copy.deepcopy(operation)
            replacement = operation.get("replacement")
            if with_code and replacement:
                method = replacement["method"]
                (ws / "out" / "code").mkdir(parents=True, exist_ok=True)
                (ws / "out" / "code" / f"{method}.py").write_text(
                    replacement.pop("method_code"), encoding="utf-8")
                replacement["method_code_file"] = f"code/{method}.py"
                name = method
            else:
                name = str(operation.get("source") or index).replace("/", "_")
            ctx.dump(ws / "out" / "ops" / f"{index:03d}_{name}.json", operation)

    def _batch(self, ws: Path):
        for workflow in ctx.load_context(ws)["batch"]:
            wid = str(workflow["id"])
            ctx.dump(ws / "out" / "extractions" / f"{wid}.json",
                     _load(FIXTURE / "extract" / f"{wid}.json"))
        proposal = _load(FIXTURE / "build" / "batch_000.json")
        self._write_ops(ws, proposal["operations"], with_code=True)
        ctx.dump(ws / "out" / "workflow_attribution.json", proposal["workflow_attribution"])
        ctx.dump(ws / "out" / "candidate_attribution.json", proposal["candidate_attribution"])

    def _site(self, ws: Path):
        self._write_ops(ws, _load(FIXTURE / "consolidate" / "proposal.json")["operations"],
                        with_code=False)


@pytest.fixture
def built(tmp_path, monkeypatch):
    monkeypatch.setattr("skill_agent.runner.WebwrightRunner", ReplayJudge)
    ReplayJudge.calls = []
    log: list[str] = []
    library = tmp_path / "map"
    result = build_mod.build_site(
        lambda lib, number: ScriptedAgent(lib, number, log),
        site="map", workflows=_load(WORKFLOWS), library=library, runs=tmp_path / "runs",
        batch_size=8, seed=20260810, max_attempts=2)
    return result, library, log


def test_reproduces_the_scripted_package(built):
    _, library, _ = built
    expected = _load(FIXTURE / "expected.json")
    index = _load(library / "final_candidate" / "index.json")
    assert index["package_sha256"] == expected["package_sha256"]
    assert [p["primitive_id"] for p in index["primitives"]] == expected["primitive_ids"]
    assert index["root_class"] == expected["root_class"]


def test_each_episode_verified_before_the_driver_committed(built):
    _, _, log = built
    assert log == ["batch: verify -> ready", "site: verify -> ready"]


def test_both_judges_ran_as_separate_episodes(built):
    """One completeness review over the extractions, one boundary judge over the proposal.
    The driver's re-verify reuses both cached rulings rather than spawning them again."""
    assert ReplayJudge.calls == ["extraction_review", "judge"]


def test_writes_the_scripted_artifact_layout(built):
    result, library, _ = built
    for relative in (
        "config.json", "workflow_order.json", "audit.json", "pool.json",
        "pre_consolidation/primitive_pool.json",
        "batches/batch_000/proposal.json", "batches/batch_000/validation.json",
        "batches/batch_000/quality_verdicts.json", "batches/batch_000/primitive_diff.json",
        "batches/batch_000/workflow_attribution.json",
        "batches/batch_000/snapshot/primitive_pool.json",
        "consolidation/proposal.json", "consolidation/coverage.json",
        "final_candidate/package.py", "final_candidate/index.json", "final_candidate/review.md",
    ):
        assert (library / relative).exists(), f"missing {relative}"
    for workflow_id in ("task76_t65", "task81_t72", "task85_t64"):
        assert (library / "extractions" / workflow_id / "extraction.json").exists()
    assert result["final_count"] == 2


def test_episodes_are_resumable(built, tmp_path):
    _, library, _ = built
    log: list[str] = []
    build_mod.build_site(
        lambda lib, number: ScriptedAgent(lib, number, log),
        site="map", workflows=_load(WORKFLOWS), library=library, runs=tmp_path / "again",
        batch_size=8, seed=20260810, max_attempts=2)
    assert log == [], "an applied batch and a rendered site must not be re-run"


class LazyAgent(ScriptedAgent):
    """Declares itself done without producing anything."""

    def _batch(self, ws: Path):
        return


def test_an_unverified_episode_commits_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("skill_agent.runner.WebwrightRunner", ReplayJudge)
    library = tmp_path / "map"
    with pytest.raises(ValueError, match="batch 0 failed"):
        build_mod.build_site(
            lambda lib, number: LazyAgent(lib, number, []),
            site="map", workflows=_load(WORKFLOWS), library=library, runs=tmp_path / "runs",
            batch_size=8, seed=20260810, max_attempts=1)
    assert not (library / "batches").exists(), "nothing may reach the library"
    assert not ctx.pool_path(library).exists()
