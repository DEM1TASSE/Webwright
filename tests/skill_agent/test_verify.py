"""Contracts of the one command the agent drives itself with.

`verify` is the only thing standing between a confident agent and a library full of unchecked
primitives, so it has to derive everything from disk: what is still missing, whether the
composed proposal validates, and whether an independent judge accepted it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_agent import context as ctx
from skill_agent import verify as verify_mod

WORKFLOW = {"id": "task1_t2", "task_id": 1, "template_id": 2, "site": "gitlab",
            "intent": "how many commits", "code": "print('x')"}
SKIP_EXTRACTION = {"decision": "SKIP", "candidates": [], "skip_category": "BLOCKED",
                   "reason": "login was blocked"}


@pytest.fixture
def episode(tmp_path, monkeypatch):
    """A batch workspace plus the environment the driver would have forwarded."""
    workspace, library = tmp_path / "ws", tmp_path / "lib"
    (workspace / "in").mkdir(parents=True)
    (workspace / "out").mkdir(parents=True)
    ctx.dump(workspace / "in" / "context.json",
             {"mode": "batch", "site": "gitlab", "batch": [WORKFLOW],
              "all_workflows": {WORKFLOW["id"]: WORKFLOW}})
    library.mkdir(parents=True)
    monkeypatch.setenv(ctx.ENV_LIBRARY, str(library))
    monkeypatch.setenv(ctx.ENV_BATCH, "0")
    monkeypatch.setenv(ctx.ENV_REPO_ROOT, str(Path(__file__).parents[2]))
    monkeypatch.setenv(ctx.ENV_MODEL_CONFIG, "unused.yaml")
    return workspace, library


def test_reports_a_missing_extraction_by_name(episode):
    workspace, _ = episode
    code, steps, errors, _ = verify_mod.run(workspace, with_judge=False)
    assert code == 1
    assert f"out/extractions/{WORKFLOW['id']}.json does not exist" in steps[0]
    assert any("blocked until every workflow is extracted" in s for s in steps)


def test_does_not_reach_the_build_step_while_an_extraction_is_bad(episode):
    workspace, _ = episode
    ctx.dump(workspace / "out" / "extractions" / f"{WORKFLOW['id']}.json",
             {"decision": "CANDIDATES", "candidates": [{"candidate_id": "x"}]})
    _, _, errors, extra = verify_mod.run(workspace, with_judge=False)
    assert errors and all(e.startswith(f"extract {WORKFLOW['id']}") for e in errors)
    assert "proposal" not in extra, "a broken extraction must not be composed over"


def test_unparsable_extraction_is_an_error_not_a_crash(episode):
    workspace, _ = episode
    path = workspace / "out" / "extractions" / f"{WORKFLOW['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    code, _, errors, _ = verify_mod.run(workspace, with_judge=False)
    assert code == 1 and "not valid JSON" in errors[0]


def test_asks_for_operation_files_once_extractions_are_accepted(episode):
    workspace, _ = episode
    ctx.dump(workspace / "out" / "extractions" / f"{WORKFLOW['id']}.json", SKIP_EXTRACTION)
    code, steps, errors, _ = verify_mod.run(workspace, with_judge=False)
    assert code == 1
    assert f"[x] extract {WORKFLOW['id']}" in steps[0]
    assert any("out/ops/" in e for e in errors)


class TestComposition:
    def _ops(self, tmp_path: Path, name: str, op: dict) -> None:
        ctx.dump(tmp_path / "out" / "ops" / name, op)

    def test_inlines_method_code_from_a_python_file(self, tmp_path):
        (tmp_path / "out" / "code").mkdir(parents=True)
        (tmp_path / "out" / "code" / "list_commits.py").write_text(
            "def list_commits(self, project):\n    return []\n", encoding="utf-8")
        self._ops(tmp_path, "000_add.json", {"op": "ADD", "replacement": {
            "primitive_id": "gitlab/list_commits", "method": "list_commits",
            "method_code_file": "code/list_commits.py"}})
        proposal, errors, index_map = verify_mod.compose(tmp_path)
        assert errors == []
        replacement = proposal["operations"][0]["replacement"]
        assert replacement["method_code"].startswith("def list_commits(self, project):")
        assert "method_code_file" not in replacement
        assert index_map[0]["primitive_id"] == "gitlab/list_commits"

    def test_operation_index_follows_sorted_filename_order(self, tmp_path):
        for name, pid in (("010_b.json", "s/b"), ("000_a.json", "s/a"), ("020_c.json", "s/c")):
            self._ops(tmp_path, name, {"op": "ADD", "replacement": {
                "primitive_id": pid, "method": pid[-1], "method_code": "def x(self): ..."}})
        proposal, errors, _ = verify_mod.compose(tmp_path)
        assert errors == []
        assert [op["replacement"]["primitive_id"] for op in proposal["operations"]] == \
               ["s/a", "s/b", "s/c"]

    def test_split_replacements_each_get_their_code(self, tmp_path):
        (tmp_path / "out" / "code").mkdir(parents=True)
        for name in ("one", "two"):
            (tmp_path / "out" / "code" / f"{name}.py").write_text(
                f"def {name}(self): ...\n", encoding="utf-8")
        self._ops(tmp_path, "000_split.json", {"op": "SPLIT", "source": "s/old", "replacements": [
            {"primitive_id": "s/f/one", "method_code_file": "code/one.py"},
            {"primitive_id": "s/f/two", "method_code_file": "code/two.py"}]})
        proposal, errors, _ = verify_mod.compose(tmp_path)
        assert errors == []
        assert [r["method_code"].strip() for r in proposal["operations"][0]["replacements"]] == \
               ["def one(self): ...", "def two(self): ..."]

    @pytest.mark.parametrize("code_file, expected", [
        ("code/nope.py", "not found"),
        ("../../escape.py", "must stay inside out/"),
    ])
    def test_bad_code_file_refs_are_reported(self, tmp_path, code_file, expected):
        self._ops(tmp_path, "000_add.json",
                  {"op": "ADD", "replacement": {"primitive_id": "s/x", "method_code_file": code_file}})
        _, errors, _ = verify_mod.compose(tmp_path)
        assert any(expected in e for e in errors), errors

    def test_setting_both_code_forms_is_an_error(self, tmp_path):
        (tmp_path / "out" / "code").mkdir(parents=True)
        (tmp_path / "out" / "code" / "x.py").write_text("def x(self): ...\n", encoding="utf-8")
        self._ops(tmp_path, "000_add.json", {"op": "ADD", "replacement": {
            "primitive_id": "s/x", "method_code": "def x(self): ...",
            "method_code_file": "code/x.py"}})
        _, errors, _ = verify_mod.compose(tmp_path)
        assert any("keep only one" in e for e in errors), errors


def test_judge_verdicts_are_reused_for_an_unchanged_proposal(episode, monkeypatch):
    """Re-verifying unchanged work must not burn another judge episode."""
    workspace, _ = episode
    calls = []

    class CountingJudge:
        def __init__(self, **_):
            pass

        def run_episode(self, *, stage, task, workspace, step_limit, max_output_tokens):
            calls.append(stage)
            ctx.dump(Path(workspace) / "out" / "verdicts.json",
                     {"verdicts": [], "rejection_verdicts": []})
            from skill_agent.runner import EpisodeResult
            return EpisodeResult(stage=stage, workspace=Path(workspace),
                                 exit_status="Submitted", api_calls=1)

    monkeypatch.setattr("skill_agent.runner.WebwrightRunner", CountingJudge)
    proposal = {"operations": [], "candidate_attribution": []}
    context = ctx.load_context(workspace)
    assert verify_mod.judge(workspace, proposal, context)[1] == []
    assert verify_mod.judge(workspace, proposal, context)[1] == []
    assert len(calls) == 1, "the second call should reuse the cached verdict"

    verify_mod.judge(workspace, {"operations": [], "candidate_attribution": [{"x": 1}]}, context)
    assert len(calls) == 2, "a changed proposal must be judged again"


def test_the_judge_checks_its_own_verdicts_with_the_same_command(tmp_path, monkeypatch):
    monkeypatch.setenv(ctx.ENV_LIBRARY, str(tmp_path / "lib"))
    (tmp_path / "in").mkdir(parents=True)
    (tmp_path / "out").mkdir(parents=True)
    operations = [{"op": "ADD", "replacement": {"primitive_id": "s/x"}}]
    ctx.dump(tmp_path / "in" / "context.json",
             {"mode": "judge", "site": "gitlab", "operations": operations,
              "candidate_attribution": []})

    code, _, errors, _ = verify_mod.run(tmp_path, with_judge=False)
    assert code == 1 and "verdicts.json" in errors[0]

    # A FAIL is a legitimate ruling, so the verdict file itself is well-formed.
    ctx.dump(tmp_path / "out" / "verdicts.json", {
        "verdicts": [{"operation_index": 0, "verdict": "FAIL", "reason": "owns task filtering"}],
        "rejection_verdicts": []})
    code, _, errors, _ = verify_mod.run(tmp_path, with_judge=False)
    assert (code, errors) == (0, [])


def test_outside_an_episode_it_fails_with_a_readable_message(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(ctx.ENV_LIBRARY, raising=False)
    assert verify_mod.main(["--workspace", str(tmp_path)]) == 2
    assert "context.json" in capsys.readouterr().out


class TestExtractionReview:
    """Extraction is where capability is lost silently: everything downstream only sees what
    was enumerated, so no later check can notice an omission. Two static approaches failed --
    matching every string literal was noise, reading call-site arguments was too sparse
    because these workflows assemble URLs into variables -- so an independent reader rules.
    """

    def _reviewer(self, ruling, calls):
        class Reviewer:
            def __init__(self, **_):
                pass

            def run_episode(self, *, stage, task, workspace, step_limit, max_output_tokens):
                calls.append(stage)
                ctx.dump(Path(workspace) / "out" / "extraction_review.json", ruling)
                from skill_agent.runner import EpisodeResult
                return EpisodeResult(stage=stage, workspace=Path(workspace),
                                     exit_status="Submitted", api_calls=1)
        return Reviewer

    def test_an_incomplete_extraction_blocks_the_build(self, episode, monkeypatch):
        workspace, _ = episode
        calls = []
        monkeypatch.setattr("skill_agent.runner.WebwrightRunner", self._reviewer({"reviews": [
            {"workflow_id": WORKFLOW["id"], "verdict": "INCOMPLETE",
             "missed": [{"capability": "reading project members", "evidence": "goto members"}],
             "reason": "the source visits two areas, one became a candidate"}]}, calls))
        ctx.dump(workspace / "out" / "extractions" / f"{WORKFLOW['id']}.json", SKIP_EXTRACTION)

        code, steps, errors, _ = verify_mod.run(workspace)
        assert code == 1
        assert any("reading project members" in e for e in errors)
        assert any("blocked until every demonstrated capability" in s for s in steps)
        assert calls == ["extraction_review"], "the boundary judge is not reached yet"

    def test_a_complete_extraction_lets_the_build_be_evaluated(self, episode, monkeypatch):
        workspace, _ = episode
        calls = []
        monkeypatch.setattr("skill_agent.runner.WebwrightRunner", self._reviewer({"reviews": [
            {"workflow_id": WORKFLOW["id"], "verdict": "COMPLETE", "missed": [],
             "reason": "read the source"}]}, calls))
        ctx.dump(workspace / "out" / "extractions" / f"{WORKFLOW['id']}.json", SKIP_EXTRACTION)

        _, steps, errors, _ = verify_mod.run(workspace)
        assert any("nothing demonstrated was missed" in s for s in steps)
        assert any("out/ops/" in e for e in errors), "it moves on to asking for operations"

    def test_a_review_that_skips_a_workflow_is_rejected(self, episode, monkeypatch):
        workspace, _ = episode
        monkeypatch.setattr("skill_agent.runner.WebwrightRunner",
                            self._reviewer({"reviews": []}, []))
        ctx.dump(workspace / "out" / "extractions" / f"{WORKFLOW['id']}.json", SKIP_EXTRACTION)
        _, _, errors, _ = verify_mod.run(workspace)
        assert any("must cover every workflow exactly once" in e for e in errors)

    def test_the_reviewer_checks_its_own_ruling(self, tmp_path, monkeypatch):
        monkeypatch.setenv(ctx.ENV_LIBRARY, str(tmp_path / "lib"))
        (tmp_path / "in").mkdir(parents=True)
        (tmp_path / "out").mkdir(parents=True)
        ctx.dump(tmp_path / "in" / "context.json",
                 {"mode": "extraction_review", "site": "gitlab", "extractions": []})

        code, _, errors, _ = verify_mod.run(tmp_path, with_judge=False)
        assert code == 1 and "extraction_review.json" in errors[0]

        ctx.dump(tmp_path / "out" / "extraction_review.json", {"reviews": [
            {"workflow_id": "w1", "verdict": "INCOMPLETE", "missed": []}]})
        _, _, errors, _ = verify_mod.run(tmp_path, with_judge=False)
        assert any("needs at least one missed entry" in e for e in errors)

        ctx.dump(tmp_path / "out" / "extraction_review.json", {"reviews": [
            {"workflow_id": "w1", "verdict": "COMPLETE", "missed": [], "reason": "checked"}]})
        code, _, errors, _ = verify_mod.run(tmp_path, with_judge=False)
        assert (code, errors) == (0, [])
