from webwright.skill_factory.audited_primitive_retrieve import (
    draft_scratch_plan, render_audited_primitive_hint, retrieve_audited_primitives,
)


def _library(tmp_path):
    root = tmp_path / "gitlab/final_candidate"
    root.mkdir(parents=True)
    primitive = {
        "primitive_id": "gitlab/commits/list_commits", "feature": "commits",
        "method": "list_commits", "capability": "List GitLab commits.",
        "method_code": "def list_commits(self, project):\n    return []\n",
        "owns": ["GitLab commit acquisition"], "does_not_own": ["ranking"],
        "input_contract": {"project": "str"}, "output_contract": {"type": "list"},
        "requires": [], "provides": ["commit_records"], "supported_patterns": [],
        "guarantees": {"collection_scope": "page", "completeness": "partial"},
    }
    (root / "index.json").write_text(__import__("json").dumps({
        "site": "gitlab", "status": "candidate", "approved": False,
        "primitives": [primitive],
    }))
    return tmp_path


def test_metadata_route_then_full_selected_code_injection(tmp_path):
    library = _library(tmp_path)
    seen = {}

    def decide(task, metadata):
        seen["metadata"] = metadata
        assert "method_code" not in metadata[0]
        assert metadata[0]["guarantees"]["completeness"] == "partial"
        return {"decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
                "reason": "useful", "remaining_gap": ["rank commits"]}

    result = retrieve_audited_primitives(
        "top commits", library, site="gitlab", decide_fn=decide
    )
    hint = render_audited_primitive_hint(result)
    assert result.decision == "adapt"
    assert "def list_commits" in hint
    assert "rank commits" in hint
    assert "primitive-source: gitlab/commits/list_commits sha256:" in hint


def test_skip_injects_no_code(tmp_path):
    result = retrieve_audited_primitives(
        "unrelated", _library(tmp_path), site="gitlab",
        decide_fn=lambda *_: {"decision": "skip", "primitive_ids": []},
    )
    assert result.primitives == []
    assert render_audited_primitive_hint(result) == ""


def _accept_verdict(*_):
    return {
        "verdict": "accept",
        "checks": {
            "input_reachability": "pass",
            "guarantee_sufficiency": "pass",
            "closed_acquisition": "pass",
        },
        "closed_acquisitions": ["GitLab commit acquisition"],
        "reason": "the primitive closes typed commit acquisition",
    }


def test_contract_verifier_accepts_one_closed_local_acquisition(tmp_path):
    result = retrieve_audited_primitives(
        "top commits", _library(tmp_path), site="gitlab",
        decide_fn=lambda *_: {
            "decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
            "remaining_gap": ["rank commits"],
        },
        verify_fn=_accept_verdict,
    )
    assert result.decision == "adapt"
    assert result.contract_verdict["verdict"] == "accept"
    assert "Contract verifier:" in render_audited_primitive_hint(result)


def test_contract_verifier_rejects_insufficient_guarantee(tmp_path):
    result = retrieve_audited_primitives(
        "all commits", _library(tmp_path), site="gitlab",
        decide_fn=lambda *_: {
            "decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
        },
        verify_fn=lambda *_: {
            "verdict": "reject",
            "checks": {
                "input_reachability": "pass",
                "guarantee_sufficiency": "fail",
                "closed_acquisition": "pass",
            },
            "closed_acquisitions": ["one result page"],
            "reason": "page-scoped output cannot prove an exhaustive set",
        },
    )
    assert result.decision == "skip"
    assert result.primitives == []
    assert result.contract_verdict["checks"]["guarantee_sufficiency"] == "fail"
    assert render_audited_primitive_hint(result) == ""


def test_contract_verifier_fails_closed_on_malformed_output(tmp_path):
    result = retrieve_audited_primitives(
        "top commits", _library(tmp_path), site="gitlab",
        decide_fn=lambda *_: {
            "decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
        },
        verify_fn=lambda *_: {"verdict": "accept"},
    )
    assert result.decision == "skip"
    assert result.contract_verdict["verdict"] == "accept"
    assert result.contract_verdict["checks"] == {}


def _plan():
    return {
        "site": "gitlab", "task": "top commits",
        "steps": [
            {"id": "S1", "action": "Acquire commit records", "inputs": ["project"],
             "outputs": ["commit_records"], "acceptance_checks": ["records complete"]},
            {"id": "S2", "action": "Rank records", "inputs": ["commit_records"],
             "outputs": ["answer"], "acceptance_checks": []},
        ],
        "required_facts": [],
    }


def test_scratch_plan_is_created_without_library_assumptions():
    plan = draft_scratch_plan(
        "top commits", site="gitlab",
        plan_fn=lambda task, site: {
            "steps": [{"id": "S1", "action": "Acquire commits", "outputs": ["commits"]}],
            "required_facts": [{"id": "commits", "needed_by_step": "S1",
                                "description": "GitLab commit records"}],
        },
    )
    assert plan["task"] == "top commits"
    assert plan["steps"][0]["id"] == "S1"
    assert plan["required_facts"][0]["id"] == "commits"


def test_adapt_requires_a_valid_local_patch(tmp_path):
    result = retrieve_audited_primitives(
        "top commits", _library(tmp_path), site="gitlab", scratch_plan=_plan(),
        decide_fn=lambda *_: {
            "decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
            "reason": "related but no replaceable step", "patches": [],
        },
    )
    assert result.decision == "skip"
    assert result.primitives == []
    hint = render_audited_primitive_hint(result)
    assert "Frozen scratch-first plan" in hint
    assert "def list_commits" not in hint


def test_context_only_patch_is_rejected(tmp_path):
    result = retrieve_audited_primitives(
        "top commits", _library(tmp_path), site="gitlab", scratch_plan=_plan(),
        decide_fn=lambda *_: {
            "decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
            "patches": [{"scratch_step_id": "S1",
                         "primitive_id": "gitlab/commits/list_commits",
                         "replaces": [], "preserves": ["original S1"],
                         "acceptance_checks": ["might help"]}],
        },
    )
    assert result.decision == "skip"
    assert result.patches == []


def test_step_id_only_patch_is_rejected(tmp_path):
    result = retrieve_audited_primitives(
        "top commits", _library(tmp_path), site="gitlab", scratch_plan=_plan(),
        decide_fn=lambda *_: {
            "decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
            "patches": [{"scratch_step_id": "S1",
                         "primitive_id": "gitlab/commits/list_commits",
                         "replaces": ["S1"], "acceptance_checks": ["records complete"]}],
        },
    )
    assert result.decision == "skip"


def test_adapt_is_rendered_as_local_patch_with_fallback(tmp_path):
    result = retrieve_audited_primitives(
        "top commits", _library(tmp_path), site="gitlab", scratch_plan=_plan(),
        decide_fn=lambda *_: {
            "decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
            "reason": "replaces acquisition only", "remaining_gap": ["ranking"],
            "patches": [{
                "scratch_step_id": "S1", "primitive_id": "gitlab/commits/list_commits",
                "replaces": ["commit acquisition"], "preserves": ["S2 ranking"],
                "acceptance_checks": ["records complete"],
                "avoids_when_accepted": ["manual commit-page traversal"],
                "fallback": "run original S1",
            }],
        },
    )
    assert result.decision == "adapt"
    assert result.patches[0]["scratch_step_id"] == "S1"
    hint = render_audited_primitive_hint(result)
    assert "Do not redesign" in hint
    assert "run original S1" in hint
    assert "def list_commits" in hint
    assert "successful output still requires the original acquisition" in hint
    assert "primitive_execution_trace.jsonl" in hint


def test_metadata_only_ablation_renders_contract_without_code(tmp_path):
    result = retrieve_audited_primitives(
        "top commits", _library(tmp_path), site="gitlab", scratch_plan=_plan(),
        decide_fn=lambda *_: {
            "decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
            "patches": [{
                "scratch_step_id": "S1", "primitive_id": "gitlab/commits/list_commits",
                "replaces": ["commit acquisition"],
                "acceptance_checks": ["records complete"],
                "avoids_when_accepted": ["manual commit-page traversal"],
            }],
        },
    )
    hint = render_audited_primitive_hint(result, include_code=False)
    assert "input_contract:" in hint
    assert "Implementation withheld for metadata-only ablation" in hint
    assert "def list_commits" not in hint


def test_patch_without_avoidable_scratch_work_is_rejected(tmp_path):
    result = retrieve_audited_primitives(
        "top commits", _library(tmp_path), site="gitlab", scratch_plan=_plan(),
        decide_fn=lambda *_: {
            "decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
            "patches": [{
                "scratch_step_id": "S1", "primitive_id": "gitlab/commits/list_commits",
                "replaces": ["probe the commit endpoint"],
                "acceptance_checks": ["records complete"],
                "fallback": "run original S1",
            }],
        },
    )
    assert result.decision == "skip"
    assert result.patches == []
