"""Replay a recorded scripted build through the agentic driver.

The fixture holds the artifacts the scripted pipeline's LLM calls actually produced for the Map
site in ``audited_site_library_v2``. A fake runner serves them instead of calling a model, so this
exercises every non-model part of the port — staging, validation, apply, consolidate, render — and
asserts the driver reproduces the scripted library's package byte-for-byte.

If this test fails, the port changed pipeline semantics, not just the interface.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_agent.build import build_site
from skill_agent.runner import EpisodeResult

FIXTURE = Path(__file__).parent / "fixtures" / "replay_map"
WORKFLOWS = Path(__file__).parents[2] / "skill_agent" / "inputs" / "workflows" / "map.json"


class ReplayRunner:
    """Serves recorded stage artifacts; records what it was asked for."""

    def __init__(self, fixture: Path):
        self.fixture = fixture
        self.calls: list[tuple[str, str]] = []

    def run_episode(self, *, stage, task, workspace, step_limit, max_output_tokens):
        workspace = Path(workspace)
        context = json.loads((workspace / "in" / "context.json").read_text(encoding="utf-8"))
        if stage == "extract":
            key = str(context["workflow"]["id"])
            source = self.fixture / "extract" / f"{key}.json"
        elif stage == "build":
            key = "batch_000"
            source = self.fixture / "build" / "batch_000.json"
        elif stage == "quality":
            key = "batch_000"
            source = self.fixture / "quality" / "batch_000.json"
        else:
            key = "consolidate"
            source = self.fixture / "consolidate" / "proposal.json"

        self.calls.append((stage, key))
        artifact = json.loads(source.read_text(encoding="utf-8"))
        target = workspace / "out" / {
            "extract": "extraction.json", "build": "proposal.json",
            "quality": "verdicts.json", "consolidate": "proposal.json",
        }[stage]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        return EpisodeResult(stage=stage, workspace=workspace, exit_status="Submitted",
                             api_calls=1, final_response="replayed")


@pytest.fixture(scope="module")
def replayed(tmp_path_factory):
    workflows = json.loads(WORKFLOWS.read_text(encoding="utf-8"))
    root = tmp_path_factory.mktemp("replay")
    runner = ReplayRunner(FIXTURE)
    result = build_site(
        runner, site="map", workflows=workflows,
        output=root / "map", runs=root / "runs" / "map",
        batch_size=8, seed=20260810, max_attempts=3,
    )
    return runner, result, root / "map"


def test_reproduces_scripted_package(replayed):
    _, _, output = replayed
    expected = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))
    index = json.loads((output / "final_candidate" / "index.json").read_text(encoding="utf-8"))
    assert index["package_sha256"] == expected["package_sha256"]
    assert [p["primitive_id"] for p in index["primitives"]] == expected["primitive_ids"]
    assert index["root_class"] == expected["root_class"]
    assert index["status"] == "candidate" and index["approved"] is False


def test_runs_every_stage_once(replayed):
    runner, _, _ = replayed
    stages = [stage for stage, _ in runner.calls]
    assert stages.count("extract") == 3, "one extract episode per workflow"
    assert stages.count("build") == 1
    assert stages.count("quality") == 1, "the gate runs as its own episode"
    assert stages.count("consolidate") == 1


def test_writes_the_scripted_artifact_layout(replayed):
    _, result, output = replayed
    for relative in (
        "config.json", "workflow_order.json", "audit.json",
        "pre_consolidation/primitive_pool.json",
        "batches/batch_000/proposal.json", "batches/batch_000/validation.json",
        "batches/batch_000/primitive_diff.json", "batches/batch_000/workflow_attribution.json",
        "batches/batch_000/snapshot/primitive_pool.json",
        "consolidation/proposal.json", "consolidation/coverage.json",
        "final_candidate/package.py", "final_candidate/index.json", "final_candidate/review.md",
    ):
        assert (output / relative).exists(), f"missing {relative}"
    for workflow_id in ("task76_t65", "task81_t72", "task85_t64"):
        assert (output / "extractions" / workflow_id / "validation.json").exists()
    assert result["final_count"] == 2
    assert result["status"] == "candidate"


def test_stages_source_code_for_the_agent(replayed):
    """Every episode must be able to read the real workflow code from its workspace."""
    _, _, output = replayed
    runs = output.parent / "runs" / "map"
    sources = sorted(p.name for p in (runs / "build" / "batch_000" / "attempt_1" / "in" / "sources").glob("*.py"))
    assert sources == ["task76_t65.py", "task81_t72.py", "task85_t64.py"]
    pooled_code = sorted(p.name for p in (runs / "consolidate" / "attempt_1" / "in" / "code").glob("*.py"))
    assert pooled_code, "consolidate must see the pooled method bodies as .py files"


class FlakyGateRunner(ReplayRunner):
    """The gate agent botches its own artifact once (the real failure mode: a heredoc
    terminator with a command appended, so the file gets command text written into it)."""

    def run_episode(self, *, stage, task, workspace, step_limit, max_output_tokens):
        if stage == "quality" and not any(s == "quality" for s, _ in self.calls):
            self.calls.append(("quality", "botched"))
            out = Path(workspace) / "out"
            out.mkdir(parents=True, exist_ok=True)
            (out / "verdicts.json").write_text(
                '{"verdicts": []}\nJSON && python -m skill_agent.check quality\n', encoding="utf-8")
            return EpisodeResult(stage=stage, workspace=Path(workspace),
                                 exit_status="Submitted", api_calls=1)
        return super().run_episode(stage=stage, task=task, workspace=workspace,
                                   step_limit=step_limit, max_output_tokens=max_output_tokens)


def test_a_botched_gate_artifact_retries_the_gate_not_the_build(tmp_path):
    workflows = json.loads(WORKFLOWS.read_text(encoding="utf-8"))
    runner = FlakyGateRunner(FIXTURE)
    build_site(runner, site="map", workflows=workflows, output=tmp_path / "map",
               runs=tmp_path / "runs", batch_size=8, seed=20260810, max_attempts=3)

    stages = [stage for stage, _ in runner.calls]
    assert stages.count("build") == 1, "a malformed verdicts file must not cost a build regeneration"
    assert stages.count("quality") == 2, "the gate episode retries on its own"
    index = json.loads((tmp_path / "map" / "final_candidate" / "index.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))
    assert index["package_sha256"] == expected["package_sha256"]


def test_extract_stage_is_resumable(replayed, tmp_path):
    """A cached accepted extraction must not re-run its episode."""
    _, _, output = replayed
    workflows = json.loads(WORKFLOWS.read_text(encoding="utf-8"))
    runner = ReplayRunner(FIXTURE)
    build_site(runner, site="map", workflows=workflows, output=output,
               runs=tmp_path / "runs", batch_size=8, seed=20260810, max_attempts=3)
    assert [stage for stage, _ in runner.calls].count("extract") == 0
