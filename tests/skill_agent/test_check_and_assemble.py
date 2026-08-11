"""Unit tests for the two commands the agent drives itself with."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_agent import assemble as assemble_mod
from skill_agent import check as check_mod

WORKFLOW = {
    "id": "task1_t2", "task_id": 1, "template_id": 2, "site": "gitlab",
    "intent": "how many commits", "code": "print('x')",
}


def _workspace(tmp_path: Path, context: dict) -> Path:
    (tmp_path / "in").mkdir(parents=True, exist_ok=True)
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    (tmp_path / "in" / "context.json").write_text(json.dumps(context), encoding="utf-8")
    return tmp_path


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class TestCheck:
    def test_missing_artifact_is_an_error_not_a_crash(self, tmp_path):
        workspace = _workspace(tmp_path, {"site": "gitlab", "workflow": WORKFLOW})
        code, report = check_mod.run("extract", workspace)
        assert code == 1
        assert not report["accepted"]
        assert "missing artifact" in report["errors"][0]

    def test_unparsable_artifact_reports_json_error(self, tmp_path):
        workspace = _workspace(tmp_path, {"site": "gitlab", "workflow": WORKFLOW})
        (workspace / "out" / "extraction.json").write_text("{not json", encoding="utf-8")
        code, report = check_mod.run("extract", workspace)
        assert code == 1
        assert "not valid JSON" in report["errors"][0]

    def test_accepts_a_valid_skip_extraction(self, tmp_path):
        workspace = _workspace(tmp_path, {"site": "gitlab", "workflow": WORKFLOW})
        _write(workspace / "out" / "extraction.json", {
            "decision": "SKIP", "candidates": [],
            "skip_category": "NO_REUSABLE_SITE_CAPABILITY",
            "reason": "the workflow only performs local git operations",
        })
        code, report = check_mod.run("extract", workspace)
        assert (code, report["accepted"], report["errors"]) == (0, True, [])

    def test_rejects_a_candidate_citing_the_wrong_workflow(self, tmp_path):
        workspace = _workspace(tmp_path, {"site": "gitlab", "workflow": WORKFLOW})
        _write(workspace / "out" / "extraction.json", {
            "decision": "CANDIDATES",
            "candidates": [{
                "candidate_id": "task1_t2::list_commits", "proposed_method": "list_commits",
                "capability": "list repository commits",
                "owns": ["commit list endpoint"], "does_not_own": ["counting"],
                "input_contract": {"project": "str"}, "output_contract": {"commits": "list"},
                "source_evidence": {"workflow_id": "task999_t999", "template_id": "999",
                                    "code_quote": "goto(...)", "explanation": "generalized"},
            }],
        })
        code, report = check_mod.run("extract", workspace)
        assert code == 1 and report["error_count"] >= 1

    def test_cli_exit_codes(self, tmp_path, capsys):
        workspace = _workspace(tmp_path, {"site": "gitlab", "workflow": WORKFLOW})
        assert check_mod.main(["extract", "--workspace", str(workspace)]) == 1
        assert "REJECTED" in capsys.readouterr().out
        _write(workspace / "out" / "extraction.json", {
            "decision": "SKIP", "candidates": [],
            "skip_category": "BLOCKED", "reason": "login was blocked",
        })
        assert check_mod.main(["extract", "--workspace", str(workspace)]) == 0
        assert "OK: extract accepted" in capsys.readouterr().out


class TestAssemble:
    def test_inlines_method_code_from_a_python_file(self, tmp_path):
        out = tmp_path / "out"
        (out / "code").mkdir(parents=True)
        (out / "code" / "list_commits.py").write_text(
            "def list_commits(self, project):\n    return []\n", encoding="utf-8")
        _write(out / "ops" / "000_add.json", {
            "op": "ADD",
            "replacement": {"primitive_id": "gitlab/list_commits", "method": "list_commits",
                            "method_code_file": "code/list_commits.py"},
        })
        _write(out / "workflow_attribution.json", [])
        _write(out / "candidate_attribution.json", [])

        proposal, errors, index_map = assemble_mod.assemble("build", tmp_path)
        assert errors == []
        code = proposal["operations"][0]["replacement"]["method_code"]
        assert code.startswith("def list_commits(self, project):")
        assert "method_code_file" not in proposal["operations"][0]["replacement"]
        assert index_map[0] == {"operation_index": 0, "file": "000_add.json",
                                "op": "ADD", "primitive_id": "gitlab/list_commits"}

    def test_operation_index_follows_sorted_filename_order(self, tmp_path):
        out = tmp_path / "out"
        for name, pid in (("010_b.json", "s/b"), ("000_a.json", "s/a"), ("020_c.json", "s/c")):
            _write(out / "ops" / name, {"op": "ADD", "replacement": {
                "primitive_id": pid, "method": pid.split("/")[-1], "method_code": "def x(self): ..."}})
        _write(out / "workflow_attribution.json", [])
        _write(out / "candidate_attribution.json", [])
        proposal, errors, _ = assemble_mod.assemble("build", tmp_path)
        assert errors == []
        assert [op["replacement"]["primitive_id"] for op in proposal["operations"]] == \
               ["s/a", "s/b", "s/c"]

    def test_split_replacements_each_get_their_code(self, tmp_path):
        out = tmp_path / "out"
        (out / "code").mkdir(parents=True)
        for name in ("one", "two"):
            (out / "code" / f"{name}.py").write_text(f"def {name}(self): ...\n", encoding="utf-8")
        _write(out / "ops" / "000_split.json", {
            "op": "SPLIT", "source": "s/old", "feature_assignments": [], "reason": "too broad",
            "replacements": [{"primitive_id": "s/f/one", "method_code_file": "code/one.py"},
                             {"primitive_id": "s/f/two", "method_code_file": "code/two.py"}],
        })
        proposal, errors, _ = assemble_mod.assemble("consolidate", tmp_path)
        assert errors == []
        assert [r["method_code"].strip() for r in proposal["operations"][0]["replacements"]] == \
               ["def one(self): ...", "def two(self): ..."]

    @pytest.mark.parametrize("code_file, expected", [
        ("code/nope.py", "not found"),
        ("../../escape.py", "must stay inside out/"),
    ])
    def test_bad_code_file_refs_are_reported_and_nothing_is_written(self, tmp_path, code_file, expected):
        out = tmp_path / "out"
        _write(out / "ops" / "000_add.json",
               {"op": "ADD", "replacement": {"primitive_id": "s/x", "method_code_file": code_file}})
        _write(out / "workflow_attribution.json", [])
        _write(out / "candidate_attribution.json", [])
        _, errors, _ = assemble_mod.assemble("build", tmp_path)
        assert any(expected in e for e in errors), errors
        assert assemble_mod.main(["build", "--workspace", str(tmp_path)]) == 1
        assert not (out / "proposal.json").exists()

    def test_setting_both_code_forms_is_an_error(self, tmp_path):
        out = tmp_path / "out"
        (out / "code").mkdir(parents=True)
        (out / "code" / "x.py").write_text("def x(self): ...\n", encoding="utf-8")
        _write(out / "ops" / "000_add.json", {"op": "ADD", "replacement": {
            "primitive_id": "s/x", "method_code": "def x(self): ...",
            "method_code_file": "code/x.py"}})
        _write(out / "workflow_attribution.json", [])
        _write(out / "candidate_attribution.json", [])
        _, errors, _ = assemble_mod.assemble("build", tmp_path)
        assert any("keep only one" in e for e in errors), errors

    def test_missing_attribution_file_is_reported(self, tmp_path):
        out = tmp_path / "out"
        _write(out / "ops" / "000_add.json", {"op": "ADD", "replacement": {
            "primitive_id": "s/x", "method_code": "def x(self): ..."}})
        _, errors, _ = assemble_mod.assemble("build", tmp_path)
        assert any("missing out/workflow_attribution.json" in e for e in errors), errors

    def test_empty_ops_directory_is_reported(self, tmp_path):
        (tmp_path / "out" / "ops").mkdir(parents=True)
        _, errors, _ = assemble_mod.assemble("build", tmp_path)
        assert any("no *.json operation files" in e for e in errors), errors
