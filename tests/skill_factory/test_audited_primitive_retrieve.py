from webwright.skill_factory.audited_primitive_retrieve import (
    _contract_closed_patch, draft_scratch_plan, render_audited_primitive_hint,
    retrieve_audited_primitives,
)


def _library(tmp_path):
    root = tmp_path / "gitlab/final_candidate"
    root.mkdir(parents=True)
    primitive = {
        "primitive_id": "gitlab/commits/list_commits", "feature": "commits",
        "method": "list_commits", "capability": "List GitLab commits.",
        "method_code": "async def list_commits(self, project):\n    return []\n",
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
        assert metadata[0]["browser_effects"] == {
            "navigates_live_page": False,
            "uses_browser_request_context": False,
            "may_change_session_or_page_state": False,
        }
        assert metadata[0]["guarantees"]["completeness"] == "partial"
        return {"decision": "adapt", "primitive_ids": ["gitlab/commits/list_commits"],
                "reason": "useful", "remaining_gap": ["rank commits"]}

    result = retrieve_audited_primitives(
        "top commits", library, site="gitlab", decide_fn=decide
    )
    hint = render_audited_primitive_hint(result)
    assert result.decision == "adapt"
    assert "async def list_commits" in hint
    assert "rank commits" in hint
    assert "primitive-source: gitlab/commits/list_commits sha256:" in hint
    assert "present, non-null, non-empty" in hint
    assert "immediately run a scratch acquisition" in hint
    assert "project exactly the fields the user requested" in hint
    assert "Typed canonical fields are authoritative" in hint
    assert "render explicit units" in hint
    assert "retry the same primitive" in hint
    assert "empty, unresolved, or error-marked" in hint
    assert "every retry needs a fresh acceptance check" in hint
    assert "does not turn the query family into an exhaustive" in hint
    assert "freeze the goal's immutable entity constraints" in hint
    assert "Query reformulation may omit terms to improve recall" in hint
    assert "candidate acceptance must not omit or weaken" in hint
    assert "parent, container, or related entity" in hint
    assert "Freeze any allowed spelling, abbreviation, localization" in hint
    assert "do not invent a new alias after inspecting a candidate" in hint
    assert "every frozen semantic facet" in hint
    assert "a pre-frozen alias, a typed field, stable identity/URL" in hint
    assert "it cannot establish that entity match" in hint
    assert "does not support absence proof can never justify" in hint
    assert "fallback_completed with source_independent=true" in hint
    assert "NOT_FOUND_ERROR is allowed only after such a complete fallback" in hint
    assert "structurally valid" in hint
    assert "identity, required entity kind/type/category or role" in hint
    assert "do not choose the first or highest-ranked record by default" in hint
    assert "contract-level structural checks and task-semantic checks" in hint
    assert "false result-presence flag" in hint
    assert "unresolved/error-marked form control" in hint
    assert "primitive_execution_trace.jsonl" in hint
    assert "partial answer is not SUCCESS" in hint
    assert "return NOT_FOUND_ERROR for the whole task" in hint
    assert "site/source-aligned" in hint
    assert "only when the current goal asks" in hint
    assert "canonical scalar" in hint
    assert "terminal lifecycle state" in hint
    assert "requested future event will not occur" in hint
    assert "raw backend/UTC timestamp is not authoritative" in hint
    assert "site-visible date with the scratch method" in hint


def test_late_bound_hint_requires_upstream_candidate_before_execution(tmp_path):
    result = retrieve_audited_primitives(
        "closest record", _library(tmp_path), site="gitlab",
        decide_fn=lambda *_: {
            "decision": "adapt",
            "primitive_ids": ["gitlab/commits/list_commits"],
            "late_bind_required": True,
            "late_bind_reason": "upstream candidate is open",
            "reason": "downstream acquisition", "remaining_gap": [],
        },
    )
    hint = render_audited_primitive_hint(result)
    assert "Late-binding invariant" in hint
    assert "candidate_set_ready" in hint
    assert "validated upstream candidate" in hint
    assert "category, role, unresolved name, or generic query" in hint
    assert "Do not execute the primitive merely to probe candidates" in hint


def test_skip_injects_no_code(tmp_path):
    result = retrieve_audited_primitives(
        "unrelated", _library(tmp_path), site="gitlab",
        decide_fn=lambda *_: {"decision": "skip", "primitive_ids": []},
    )
    assert result.primitives == []
    assert render_audited_primitive_hint(result) == ""


def test_missing_site_package_is_a_deterministic_skip_without_router_call(tmp_path):
    called = False

    def decide(*_):
        nonlocal called
        called = True
        raise AssertionError("router must not run when the site has no package")

    result = retrieve_audited_primitives(
        "read a reddit post", tmp_path, site="reddit", decide_fn=decide,
    )

    assert result.decision == "skip"
    assert result.primitives == []
    assert result.reason == "no generated candidate package for this site"
    assert called is False
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
                                "description": "GitLab commit records",
                                "fact_kind": "collection"}],
            "requested_output_facts": [{
                "id": "O1", "description": "top commit identifier",
                "value_type": "string", "evidence_scope": "entity_current",
            }],
        },
    )
    assert plan["task"] == "top commits"
    assert plan["steps"][0]["id"] == "S1"
    assert plan["required_facts"][0]["id"] == "commits"
    assert plan["required_facts"][0]["fact_kind"] == "collection"
    assert plan["requested_output_facts"] == [{
        "id": "O1", "description": "top commit identifier",
        "value_type": "string", "evidence_scope": "entity_current",
    }]


def test_scratch_plan_freezes_coverage_and_evidence_scope():
    plan = draft_scratch_plan(
        "highest contributor", site="gitlab",
        plan_fn=lambda *_: {
            "steps": [{"id": "S1", "action": "Acquire contributors"}],
            "required_facts": [{
                "id": "F1", "needed_by_step": "S1",
                "description": "repository-wide contributors",
                "coverage_obligation": "complete_population",
                "evidence_scope": "population",
            }],
        },
    )
    assert plan["required_facts"][0]["coverage_obligation"] == "complete_population"
    assert plan["required_facts"][0]["evidence_scope"] == "population"
    assert plan["required_facts"][0]["fact_kind"] == "field"


def _structured_plan(*, obligation="single", scope="scalar", fact_kind=None):
    return {
        "site": "site", "task": "task",
        "steps": [{"id": "S1", "action": "Acquire F1", "inputs": [],
                   "outputs": ["F1"], "acceptance_checks": ["F1 is sufficient"]}],
        "required_facts": [{
            "id": "F1", "needed_by_step": "S1", "description": "requested fact",
            "coverage_obligation": obligation, "evidence_scope": scope,
            **({"fact_kind": fact_kind} if fact_kind else {}),
        }],
    }


def _contract_primitive(*, completeness="partial", output=None):
    return {
        "output_contract": output or {
            "type": "object", "properties": {
                "records": {"type": "array", "items": {
                    "type": "object", "properties": {"value": {"type": "integer"}},
                }},
            },
        },
        "guarantees": {"completeness": completeness},
    }


def _structured_patch(*, path="records[].value", scope="scalar"):
    return {
        "scratch_step_id": "S1", "replaces_fact_ids": ["F1"],
        "output_bindings": [{"fact_id": "F1", "path": path,
                             "evidence_scope": scope}],
    }


def test_contract_closed_patch_rejects_partial_population_reducer():
    ok, reason = _contract_closed_patch(
        _structured_patch(scope="population"),
        primitive=_contract_primitive(completeness="partial"),
        scratch_plan=_structured_plan(obligation="complete_population", scope="population"),
    )
    assert ok is False
    assert "complete_population" in reason


def test_contract_closed_patch_accepts_complete_population():
    ok, _ = _contract_closed_patch(
        _structured_patch(scope="population"),
        primitive=_contract_primitive(completeness="complete"),
        scratch_plan=_structured_plan(obligation="complete_population", scope="population"),
    )
    assert ok is True


def test_contract_closed_patch_rejects_missing_output_field():
    ok, reason = _contract_closed_patch(
        _structured_patch(path="records[].transaction_color", scope="transaction_line"),
        primitive=_contract_primitive(completeness="complete"),
        scratch_plan=_structured_plan(scope="transaction_line"),
    )
    assert ok is False
    assert "schema-valid output binding" in reason


def test_contract_closed_patch_rejects_object_root_for_atomic_field():
    ok, reason = _contract_closed_patch(
        _structured_patch(path="records[]", scope="population"),
        primitive=_contract_primitive(completeness="complete"),
        scratch_plan=_structured_plan(
            obligation="complete_population", scope="population", fact_kind="field",
        ),
    )
    assert ok is False
    assert "schema-valid output binding" in reason


def test_contract_closed_patch_accepts_array_for_collection_fact():
    ok, _ = _contract_closed_patch(
        _structured_patch(path="records", scope="population"),
        primitive=_contract_primitive(completeness="complete"),
        scratch_plan=_structured_plan(
            obligation="complete_population", scope="population", fact_kind="collection",
        ),
    )
    assert ok is True


def test_contract_closed_patch_rejects_evidence_scope_mismatch():
    ok, reason = _contract_closed_patch(
        _structured_patch(scope="entity_current"),
        primitive=_contract_primitive(completeness="complete"),
        scratch_plan=_structured_plan(scope="transaction_line"),
    )
    assert ok is False
    assert "evidence scope mismatch" in reason


def test_contract_closed_patch_may_bind_fact_consumed_by_later_step():
    plan = _structured_plan(scope="scalar")
    plan["steps"].append({"id": "S2", "action": "Use F2"})
    plan["required_facts"].append({
        "id": "F2", "needed_by_step": "S2", "description": "later fact",
        "coverage_obligation": "single", "evidence_scope": "scalar",
    })
    patch = _structured_patch()
    patch["replaces_fact_ids"] = ["F2"]
    patch["output_bindings"] = [
        {"fact_id": "F2", "path": "records[].value", "evidence_scope": "scalar"},
    ]
    ok, _ = _contract_closed_patch(
        patch, primitive=_contract_primitive(completeness="complete"), scratch_plan=plan,
    )
    assert ok is True


def test_contract_closed_patch_cannot_retroactively_bind_earlier_fact():
    plan = _structured_plan(scope="scalar")
    plan["steps"].append({"id": "S2", "action": "Later acquisition"})
    patch = _structured_patch()
    patch["scratch_step_id"] = "S2"
    ok, reason = _contract_closed_patch(
        patch, primitive=_contract_primitive(completeness="complete"), scratch_plan=plan,
    )
    assert ok is False
    assert "before its frozen scratch step" in reason


def test_scratch_first_router_prompt_distinguishes_named_lookup_from_open_discovery(
    tmp_path, monkeypatch,
):
    seen = {}

    def fake_llm(system, _user):
        seen["system"] = system
        return {"decision": "skip", "primitive_ids": [], "reason": "probe"}

    monkeypatch.setattr("webwright.skill_factory.llm.llm_json", fake_llm)
    retrieve_audited_primitives(
        "route between two named places", _library(tmp_path), site="gitlab",
        scratch_plan=_plan(),
    )
    assert "finite set of fully named entities" in seen["system"]
    assert "resolved identity fields" in seen["system"]
    assert "open candidate set" in seen["system"]
    assert "output_bindings" in seen["system"]
    assert "population reducer" in seen["system"]
    assert "absent from the output schema" in seen["system"]


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


def test_use_with_structured_plan_requires_contract_closed_patch(tmp_path):
    result = retrieve_audited_primitives(
        "top commits", _library(tmp_path), site="gitlab",
        scratch_plan=_structured_plan(obligation="complete_population", scope="population"),
        decide_fn=lambda *_: {
            "decision": "use", "primitive_ids": ["gitlab/commits/list_commits"],
            "patches": [{
                "scratch_step_id": "S1", "primitive_id": "gitlab/commits/list_commits",
                "replaces": ["complete commit acquisition"],
                "acceptance_checks": ["all commits present"],
                "avoids_when_accepted": ["manual full-history traversal"],
                "replaces_fact_ids": ["F1"],
                "output_bindings": [{"fact_id": "F1", "path": "records[].value",
                                     "evidence_scope": "population"}],
            }],
        },
    )
    assert result.decision == "skip"
    assert result.primitives == []


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
    assert "fallback is complete only after the original frozen step succeeds" in hint
    assert "fallback_completed with source_independent=true" in hint
    assert "Merely writing fallback_used" in hint
    assert "cannot justify NOT_FOUND_ERROR" in hint
    assert "Final projection invariant" in hint
    assert "Do not append an unrequested count" in hint
    assert "Requested-fact ledger invariant" in hint
    assert "Check completeness before concision" in hint
    assert "Subject-lineage invariant" in hint
    assert "Semantic-reducer invariant" in hint
    assert "Preserved-effect invariant" in hint


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
