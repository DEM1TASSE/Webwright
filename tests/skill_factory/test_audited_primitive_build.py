import json
import threading

import pytest

from webwright.skill_factory.audited_primitive_build import (
    _drop_unlinked_semantic_operations, _normalize_consolidation_response,
    apply_build_operations, build_audited_site_library, partition_workflows,
    render_site_package, validate_build_proposal, validate_consolidation, validate_primitive,
)


SOURCE = """page.goto('/projects/demo/-/commits/main')
rows = page.locator('.commit-row').all_inner_texts()
records = [{"title": row, "sha": row[:8]} for row in rows]
print(records)
"""
WORKFLOWS = [{"id": "w1", "task_id": 1, "template_id": 10, "code": SOURCE},
             {"id": "w2", "task_id": 2, "template_id": 20, "code": SOURCE}]


def extraction(workflow):
    return {"decision": "CANDIDATES", "candidates": [{
        "candidate_id": f"{workflow['id']}::list_commits",
        "proposed_method": "list_commits", "capability": "List GitLab commits.",
        "owns": ["GitLab commit parsing"], "does_not_own": ["ranking"],
        "input_contract": {"project": "str"},
        "output_contract": {"type": "list[CommitRecord]"},
        "guarantees": {
            "collection_scope": "page", "completeness": "partial",
            "supports_absence_proof": False,
            "configuration": {"kind": "none", "input_field": None, "supported_values": [],
                              "coupled_site_parameters_hidden": True},
        },
        "acceptance_checks": ["the commit page loaded and parsed without error"],
        "source_evidence": {"workflow_id": workflow["id"],
                            "template_id": workflow["template_id"],
                            "code_quote": SOURCE, "explanation": "direct"},
    }]}


def primitive(pid="gitlab/list_commits", feature=None):
    value = {
        "primitive_id": pid, "method": "list_commits",
        "capability": "List typed GitLab commit records.",
        "method_code": "async def list_commits(self, project):\n    return []\n",
        "owns": ["GitLab commit selectors and parsing"],
        "does_not_own": ["task filtering and answer formatting"],
        "input_contract": {"project": "str"},
        "output_contract": {"type": "list[CommitRecord]", "fields": {"title": "str"}},
        "requires": ["authenticated_session"], "provides": ["typed_commit_records"],
        "supported_patterns": [],
        "guarantees": {
            "collection_scope": "page", "completeness": "partial",
            "supports_absence_proof": False,
            "configuration": {"kind": "none", "input_field": None, "supported_values": [],
                              "coupled_site_parameters_hidden": True},
        },
        "acceptance_checks": ["the commit page loaded and parsed without error"],
        "source_evidence": [{"workflow_id": "w1", "template_id": 10,
                             "code_quote": SOURCE,
                             "explanation": "The source directly reads and parses commit rows."}],
    }
    if feature:
        value["feature"] = feature
    return value


def test_partition_is_deterministic_and_bounded():
    assert partition_workflows(WORKFLOWS, batch_size=1, seed=7) == partition_workflows(
        list(reversed(WORKFLOWS)), batch_size=1, seed=7
    )


def test_unlinked_generated_operation_is_dropped_and_indices_are_remapped():
    raw = {
        "operations": [
            {"op": "ADD", "replacement": {"primitive_id": "gitlab/invented"}},
            {"op": "ADD", "replacement": {"primitive_id": "gitlab/list_commits"}},
        ],
        "candidate_attribution": [{
            "candidate_id": "w1::list_commits", "decision": "ADD",
            "operation_index": 1,
        }],
        "workflow_attribution": [{
            "workflow_id": "w1", "decision": "CONTRIBUTED",
            "operation_indices": [0, 1],
        }],
    }
    normalized = _drop_unlinked_semantic_operations(raw)
    assert [row["replacement"]["primitive_id"] for row in normalized["operations"]] == [
        "gitlab/list_commits"
    ]
    assert normalized["candidate_attribution"][0]["operation_index"] == 0
    assert normalized["workflow_attribution"][0]["operation_indices"] == [0]
    assert normalized["manager_normalizations"][0]["dropped"][0]["operation_index"] == 0


def test_consolidation_response_normalizes_single_operation_and_list():
    operation = {"op": "KEEP", "source": "candidate", "feature": "commits"}
    assert _normalize_consolidation_response(operation) == {"operations": [operation]}
    assert _normalize_consolidation_response([operation]) == {"operations": [operation]}


def test_bare_extraction_candidate_gets_mechanical_envelope():
    from webwright.skill_factory.audited_primitive_build import _normalize_extraction

    candidate = extraction(WORKFLOWS[0])["candidates"][0]
    assert _normalize_extraction(candidate) == {
        "decision": "CANDIDATES", "candidates": [candidate]
    }


def test_named_operation_envelope_is_canonicalized_and_audited():
    from webwright.skill_factory.audited_primitive_build import _normalize_operation_envelopes

    model_operation = {"ADD": {"replacement": primitive()}}
    value = {"operations": [model_operation]}
    normalized = _normalize_operation_envelopes(value)
    assert normalized["operations"] == [{"op": "ADD", "replacement": primitive()}]
    assert normalized["model_operations"] == [model_operation]
    assert value == {"operations": [model_operation]}


def test_workflow_attribution_is_derived_from_replacement_evidence():
    from webwright.skill_factory.audited_primitive_build import _reconcile_workflow_attribution

    proposal = {
        "operations": [{"op": "ADD", "replacement": primitive()}],
        "workflow_attribution": [
            {"workflow_id": "w1", "decision": "SKIP", "reason": "model mismatch"},
            {"workflow_id": "w2", "decision": "CONTRIBUTED", "operation_indices": [0]},
        ],
    }
    reconciled = _reconcile_workflow_attribution(proposal, WORKFLOWS)
    assert reconciled["workflow_attribution"] == [
        {"workflow_id": "w1", "decision": "CONTRIBUTED", "operation_indices": [0]},
        {"workflow_id": "w2", "decision": "SKIP",
         "reason": "No generated ADD/UPDATE replacement cites this workflow as source evidence."},
    ]
    assert reconciled["model_workflow_attribution"] == proposal["workflow_attribution"]


def test_safe_guarantee_normalization_only_weakens_invalid_absence_claim():
    from webwright.skill_factory.audited_primitive_build import (
        _normalize_safe_guarantee_weakening,
    )

    value = {"operations": [{"op": "ADD", "replacement": primitive()}]}
    value["operations"][0]["replacement"]["guarantees"].update({
        "completeness": "partial", "supports_absence_proof": True,
    })
    normalized = _normalize_safe_guarantee_weakening(value)
    assert normalized["operations"][0]["replacement"]["guarantees"][
        "supports_absence_proof"
    ] is False
    assert normalized["manager_normalizations"] == [{
        "operation_index": 0,
        "field": "guarantees.supports_absence_proof",
        "from": True,
        "to": False,
        "reason": "absence proof is impossible without complete acquisition",
    }]
    assert value["operations"][0]["replacement"]["guarantees"][
        "supports_absence_proof"
    ] is True


def test_consolidation_requires_exact_coverage():
    pool = {"gitlab/list_commits": primitive()}
    final, errors, _ = validate_consolidation(
        {"operations": []}, site="gitlab", pool=pool,
        workflows={x["id"]: x for x in WORKFLOWS},
    )
    assert not final and any("exactly once" in x for x in errors)


def test_update_keeps_identity_and_contract_but_replaces_generated_code():
    old = primitive()
    replacement = primitive()
    replacement["method_code"] = (
        "async def list_commits(self, project):\n    return [{'title': project}]\n"
    )
    replacement["source_evidence"].append({
        "workflow_id": "w2", "template_id": 20, "code_quote": SOURCE,
        "explanation": "The second workflow supports the same GitLab commit operation.",
    })
    raw = {
        "operations": [{"op": "UPDATE", "target_id": old["primitive_id"],
                        "replacement": replacement}],
        "workflow_attribution": [
            {"workflow_id": "w2", "decision": "CONTRIBUTED", "operation_indices": [0]}
        ],
    }
    accepted, errors = validate_build_proposal(
        raw, site="gitlab", batch=[WORKFLOWS[1]], pool={old["primitive_id"]: old},
        all_workflows={x["id"]: x for x in WORKFLOWS},
    )
    assert not errors
    updated, diff = apply_build_operations({old["primitive_id"]: old}, accepted)
    assert updated[old["primitive_id"]]["method_code"] == replacement["method_code"]
    assert diff[0]["before_hash"] != diff[0]["after_hash"]


def test_update_allows_only_backward_compatible_contract_widening():
    from webwright.skill_factory.audited_primitive_build import _contract_is_backward_compatible

    old = {"type": "object", "properties": {"title": {"type": "string"}},
           "required": ["title"]}
    wider = {"type": "object", "properties": {
        "title": {"type": "string"}, "sha": {"type": "string"}},
        "required": ["title", "sha"]}
    assert _contract_is_backward_compatible(old, wider, input_contract=False)
    assert not _contract_is_backward_compatible(wider, old, input_contract=False)

    old_input = {"type": "object", "properties": {"project": {"type": "string"}},
                 "required": ["project"]}
    breaking_input = {"type": "object", "properties": {
        "project": {"type": "string"}, "branch": {"type": "string"}},
        "required": ["project", "branch"]}
    assert not _contract_is_backward_compatible(
        old_input, breaking_input, input_contract=True
    )


def test_covered_candidate_cannot_drop_extracted_output_fields():
    target = primitive()
    target["output_contract"] = {
        "type": "object", "properties": {"title": {"type": "string"}}
    }
    extracted = extraction(WORKFLOWS[0])
    extracted["candidates"][0]["output_contract"] = {
        "type": "object", "properties": {
            "title": {"type": "string"}, "addressdetails": {"type": "object"}
        }
    }
    raw = {
        "operations": [],
        "workflow_attribution": [
            {"workflow_id": "w1", "decision": "SKIP", "reason": "covered"}
        ],
        "candidate_attribution": [{
            "candidate_id": "w1::list_commits", "decision": "COVERED",
            "target_id": "gitlab/list_commits", "reason": "same acquisition",
        }],
    }
    _, errors = validate_build_proposal(
        raw, site="gitlab", batch=[WORKFLOWS[0]], pool={"gitlab/list_commits": target},
        all_workflows={"w1": WORKFLOWS[0]}, extractions=[extracted],
    )
    assert any("drops extracted output fields ['addressdetails']" in error for error in errors)


def test_covered_candidate_normalizes_candidate_result_container_alias():
    target = primitive()
    target["output_contract"] = {
        "type": "object", "properties": {"results": {
            "type": "array", "items": {"type": "object", "properties": {
                "latitude": {"type": "number", "semantic_role": "location_latitude"},
                "longitude": {"type": "number", "semantic_role": "location_longitude"},
            }},
        }},
    }
    extracted = extraction(WORKFLOWS[0])
    extracted["candidates"][0]["output_contract"] = {
        "type": "array", "items": {"type": "object", "properties": {
            "lat": {"type": "string", "semantic_role": "location_latitude"},
            "lon": {"type": "string", "semantic_role": "location_longitude"},
        }},
    }
    raw = {
        "operations": [],
        "workflow_attribution": [
            {"workflow_id": "w1", "decision": "SKIP", "reason": "covered"}
        ],
        "candidate_attribution": [{
            "candidate_id": "w1::list_commits", "decision": "COVERED",
            "target_id": "gitlab/list_commits", "reason": "same acquisition",
        }],
    }
    _, errors = validate_build_proposal(
        raw, site="gitlab", batch=[WORKFLOWS[0]], pool={"gitlab/list_commits": target},
        all_workflows={"w1": WORKFLOWS[0]}, extractions=[extracted],
    )
    assert not any("drops extracted output fields" in error for error in errors)


def test_semantic_output_fields_use_explicit_roles_without_site_alias_tables():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    candidate = {"properties": {
        "local_label": {"type": "string", "semantic_role": "entity_display_name"},
    }}
    target = {"properties": {
        "remote_title": {"type": "string", "semantic_role": "entity_display_name"},
    }}
    assert _semantic_output_fields(candidate) == _semantic_output_fields(target)
    assert _semantic_output_fields({"properties": {"local_label": {}}}) == {"local_label"}


def test_required_semantic_output_fields_ignore_optional_observations_and_use_roles():
    from webwright.skill_factory.audited_primitive_build import (
        _required_semantic_output_fields,
    )

    extracted = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "local_label": {"semantic_role": "entity_display_name"},
                        "href": {"semantic_role": "entity_url"},
                    },
                    "required": ["local_label"],
                },
            }
        },
        "required": ["results"],
    }
    assert _required_semantic_output_fields(extracted) == {"entity_display_name"}


def test_semantic_output_fields_compare_flat_and_wrapped_contracts_by_role():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    extracted = {"fields": {"records": {"items": {"fields": {
        "source_value": {"semantic_role": "objective_value"},
        "source_unit": {"semantic_role": "objective_unit"},
    }}}}}
    generated = {"properties": {"results": {"items": {"properties": {
        "measurement": {"properties": {
            "value": {"semantic_role": "objective_value"},
            "unit": {"semantic_role": "objective_unit"},
        }},
    }}}}}
    assert _semantic_output_fields(extracted) <= _semantic_output_fields(generated)


def test_semantic_output_fields_ignore_compact_container_names():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    many = {"records": {"items": {"fields": {"id": {}, "detail": {}}}}}
    one = {"properties": {"record": {"properties": {"id": {}, "detail": {}}}}}
    assert _semantic_output_fields(many) == _semantic_output_fields(one) == {"id", "detail"}


def test_semantic_output_fields_hide_private_token_values_without_renaming_other_fields():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    extracted = {"properties": {
        "authenticated": {"type": "boolean"},
        "dashboard_url": {"type": "string"},
        "form_key": {"type": "string"},
    }}
    assert _semantic_output_fields(extracted) == {"authenticated", "dashboard_url"}
    assert "form_key" not in _semantic_output_fields(extracted)


def test_semantic_output_fields_do_not_guess_benchmark_specific_aliases():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    left = {"properties": {"local_name": {}}}
    right = {"properties": {"remote_title": {}}}
    assert _semantic_output_fields(left) != _semantic_output_fields(right)


def test_covered_auth_candidate_can_drop_private_token_but_not_semantic_facts():
    target = primitive()
    target["primitive_id"] = "shopping_admin/login_admin"
    target["method"] = "login_admin"
    target["output_contract"] = {"type": "object", "properties": {
        "is_authenticated": {"type": "boolean", "semantic_role": "authenticated_state"},
        "final_url": {"type": "string", "semantic_role": "result_url"},
        "form_key_present": {"type": "boolean"},
    }}
    extracted = extraction(WORKFLOWS[0])
    extracted["candidates"][0]["output_contract"] = {
        "authenticated": {"type": "boolean", "semantic_role": "authenticated_state"},
        "dashboard_url": {"type": "string", "semantic_role": "result_url"},
        "form_key": "string",
    }
    raw = {
        "operations": [],
        "workflow_attribution": [
            {"workflow_id": "w1", "decision": "SKIP", "reason": "covered"}
        ],
        "candidate_attribution": [{
            "candidate_id": "w1::list_commits", "decision": "COVERED",
            "target_id": "shopping_admin/login_admin", "reason": "same safe auth operation",
        }],
    }

    _, errors = validate_build_proposal(
        raw, site="shopping_admin", batch=[WORKFLOWS[0]],
        pool={"shopping_admin/login_admin": target},
        all_workflows={"w1": WORKFLOWS[0]}, extractions=[extracted],
    )
    assert not any("drops extracted output fields" in error for error in errors)


def test_semantic_configuration_names_its_typed_input_without_site_heuristics():
    candidate = primitive()
    candidate["input_contract"] = {
        "type": "object", "properties": {
            "variant": {"type": "string", "enum": ["compact", "expanded"]},
        },
    }
    candidate["guarantees"]["configuration"] = {
        "kind": "semantic_enum", "input_field": "variant",
        "supported_values": ["compact", "expanded"],
        "coupled_site_parameters_hidden": True,
    }
    errors = validate_primitive(
        candidate, site="gitlab", workflows={"w1": WORKFLOWS[0]},
    )
    assert not any("configuration" in error or "configured input" in error for error in errors)


def test_merge_and_split_generate_complete_classified_replacements():
    second = primitive("gitlab/get_commits")
    second["method"] = "get_commits"
    second["method_code"] = "async def get_commits(self, project):\n    return []\n"
    pool = {"gitlab/list_commits": primitive(), "gitlab/get_commits": second}
    merged = primitive("gitlab/commits/list_commits", "commits")
    final, errors, coverage = validate_consolidation(
        {"operations": [{"op": "MERGE", "sources": list(pool), "feature": "commits",
                         "replacement": merged}]},
        site="gitlab", pool=pool, workflows={x["id"]: x for x in WORKFLOWS},
    )
    assert not errors and len(final) == 1 and sorted(coverage["consumed"]) == sorted(pool)

    a = primitive("gitlab/commits/list_commits", "commits")
    b = primitive("gitlab/commits/get_commit", "commits")
    b["method"] = "get_commit"
    b["method_code"] = "async def get_commit(self, sha):\n    return {'sha': sha}\n"
    b["input_contract"] = {"sha": "str"}
    final, errors, _ = validate_consolidation(
        {"operations": [{"op": "SPLIT", "source": "gitlab/list_commits",
                         "replacements": [a, b]}]},
        site="gitlab", pool={"gitlab/list_commits": primitive()},
        workflows={x["id"]: x for x in WORKFLOWS},
    )
    assert not errors and {x["method"] for x in final} == {"list_commits", "get_commit"}


def test_split_applies_aligned_feature_assignments_to_missing_replacement_features():
    source = primitive("shopping/list_orders")
    auth = primitive("shopping/auth/get_customer_token")
    auth["method"] = "get_customer_token"
    auth["method_code"] = "async def get_customer_token(self, project):\n    return []\n"
    orders = primitive("shopping/orders/list_orders")
    orders["method"] = "list_orders"
    orders["method_code"] = "async def list_orders(self, project):\n    return []\n"

    final, errors, _ = validate_consolidation(
        {"operations": [{
            "op": "SPLIT",
            "source": "shopping/list_orders",
            "feature_assignments": ["auth", "orders"],
            "replacements": [auth, orders],
        }]},
        site="shopping",
        pool={"shopping/list_orders": source},
        workflows={x["id"]: x for x in WORKFLOWS},
    )

    assert not errors
    assert [item["feature"] for item in final] == ["auth", "orders"]


def test_split_rejects_feature_assignment_count_mismatch():
    source = primitive()
    a = primitive("gitlab/commits/list_commits", "commits")
    b = primitive("gitlab/commits/get_commit", "commits")
    b["method"] = "get_commit"
    b["method_code"] = "async def get_commit(self, project):\n    return []\n"

    _, errors, _ = validate_consolidation(
        {"operations": [{
            "op": "SPLIT", "source": "gitlab/list_commits",
            "feature_assignments": ["commits"], "replacements": [a, b],
        }]},
        site="gitlab", pool={"gitlab/list_commits": source},
        workflows={x["id"]: x for x in WORKFLOWS},
    )

    assert any("feature_assignments must align one-to-one" in error for error in errors)


def test_split_rejects_conflicting_explicit_feature_and_assignment():
    source = primitive()
    a = primitive("gitlab/commits/list_commits", "commits")
    b = primitive("gitlab/commits/get_commit", "commits")
    b["method"] = "get_commit"
    b["method_code"] = "async def get_commit(self, project):\n    return []\n"

    _, errors, _ = validate_consolidation(
        {"operations": [{
            "op": "SPLIT", "source": "gitlab/list_commits",
            "feature_assignments": ["auth", "commits"], "replacements": [a, b],
        }]},
        site="gitlab", pool={"gitlab/list_commits": source},
        workflows={x["id"]: x for x in WORKFLOWS},
    )

    assert any("conflicts with feature_assignments" in error for error in errors)


def test_split_rejects_new_secret_intermediate_input_and_complete_mode_downgrade():
    source = primitive("shopping/list_orders")
    source["guarantees"].update({
        "collection_scope": "scope", "completeness": "complete",
        "supports_absence_proof": True,
    })
    source["input_contract"] = {
        "type": "object", "properties": {
            "email": {"type": "string"}, "password": {"type": "string"},
            "fetch_all_pages": {"type": "boolean"},
        }, "required": ["email", "password"],
    }
    auth = primitive("shopping/auth/get_token", "auth")
    auth["method"] = "get_token"
    auth["method_code"] = "async def get_token(self, email, password):\n    return {}\n"
    auth["input_contract"] = {
        "type": "object", "properties": {
            "email": {"type": "string"}, "password": {"type": "string"},
        }, "required": ["email", "password"],
    }
    auth["output_contract"] = {
        "type": "object", "properties": {"is_authenticated": {"type": "boolean"}},
        "required": ["is_authenticated"],
    }
    page = primitive("shopping/orders/list_orders_page", "orders")
    page["method"] = "list_orders_page"
    page["method_code"] = "async def list_orders_page(self, bearer_token):\n    return []\n"
    page["input_contract"] = {
        "type": "object", "properties": {"bearer_token": {"type": "string"}},
        "required": ["bearer_token"],
    }
    page["guarantees"].update({"completeness": "partial", "supports_absence_proof": False})

    _, errors, _ = validate_consolidation(
        {"operations": [{
            "op": "SPLIT", "source": "shopping/list_orders",
            "replacements": [auth, page],
        }]},
        site="shopping", pool={"shopping/list_orders": source},
        workflows={x["id"]: x for x in WORKFLOWS},
    )

    assert any(
        "introduces private intermediate public inputs ['bearer_token']" in error
        for error in errors
    )
    assert any("downgrades a complete source acquisition" in error for error in errors)
    assert any("drops the source absence-proof capability" in error for error in errors)


def test_primitive_rejects_private_authentication_material_in_public_output():
    value = primitive()
    value["output_contract"] = {
        "type": "object", "properties": {"token": {"type": "string"}},
        "required": ["token"],
    }

    errors = validate_primitive(
        value, site="gitlab", workflows={"w1": WORKFLOWS[0]},
    )

    assert "output_contract exposes private authentication material: token" in errors


def test_consolidation_rejects_same_feature_and_input_contract_collision():
    second = primitive("gitlab/get_commits")
    second["method"] = "get_commits"
    second["method_code"] = "def get_commits(self, project):\n    return []\n"
    pool = {"gitlab/list_commits": primitive(), "gitlab/get_commits": second}
    _, errors, _ = validate_consolidation(
        {"operations": [
            {"op": "KEEP", "source": "gitlab/list_commits", "feature": "commits"},
            {"op": "KEEP", "source": "gitlab/get_commits", "feature": "commits"},
        ]},
        site="gitlab", pool=pool, workflows={x["id"]: x for x in WORKFLOWS},
    )
    assert any("overlapping commits primitives" in error for error in errors)


def test_operation_alias_is_canonicalized_without_changing_raw_shape(tmp_path):
    calls = []

    def fake(system, user):
        calls.append(json.loads(user))
        if calls[-1].get("review_kind") == "primitive_boundary_quality":
            return {"verdicts": [{"operation_index": 0, "verdict": "PASS", "reason": "clean"}],
                    "rejection_verdicts": []}
        if "workflow" in calls[-1]:
            return extraction(calls[-1]["workflow"])
        if "batch" in calls[-1]:
            return {
                "operations": [{"operation": "ADD", "replacement": primitive()}],
                "workflow_attribution": [
                    {"workflow_id": "w1", "decision": "CONTRIBUTED", "operation_indices": [0]},
                    {"workflow_id": "w2", "decision": "SKIP", "reason": "covered"},
                ],
                "candidate_attribution": [
                    {"candidate_id": "w1::list_commits", "decision": "ADD", "operation_index": 0},
                    {"candidate_id": "w2::list_commits", "decision": "COVERED",
                     "target_id": "gitlab/list_commits", "reason": "same operation"},
                ],
            }
        return {"operations": [{"operation": "KEEP", "source": "gitlab/list_commits",
                                 "feature": "commits"}]}

    build_audited_site_library(site="gitlab", workflows=WORKFLOWS, output=tmp_path,
                               batch_size=8, seed=3, llm_fn=fake)
    raw = json.loads((tmp_path / "batches/batch_000/proposal.json").read_text())
    assert raw["operations"][0]["operation"] == "ADD"


def test_class_manager_renders_feature_composition():
    code = render_site_package(
        "gitlab", [primitive("gitlab/commits/list_commits", "commits")]
    )
    assert "class GitLabCommits" in code
    assert "class GitLabSite" in code
    assert "self.commits = GitLabCommits(page)" in code


def test_candidate_index_composition_is_mechanical_and_rejects_conflicts(tmp_path):
    from webwright.skill_factory.audited_primitive_build import compose_candidate_indexes

    one = primitive("gitlab/commits/list_commits", "commits")
    two = primitive("gitlab/issues/list_issues", "issues")
    indexes = [
        {"site": "gitlab", "status": "candidate", "primitives": [one]},
        {"site": "gitlab", "status": "candidate", "primitives": [two]},
    ]
    result = compose_candidate_indexes(site="gitlab", indexes=indexes, output=tmp_path)
    assert [x["primitive_id"] for x in result["primitives"]] == [
        "gitlab/commits/list_commits", "gitlab/issues/list_issues"]
    assert (tmp_path / "package.py").exists()

    changed = dict(one, capability="different")
    with pytest.raises(ValueError, match="conflicting generated primitive"):
        compose_candidate_indexes(
            site="gitlab",
            indexes=[indexes[0], {"site": "gitlab", "status": "candidate",
                                  "primitives": [changed]}],
            output=tmp_path / "conflict",
        )


def test_gate_rejects_cosmetic_class_page_argument_and_answer_formatter():
    from webwright.skill_factory.audited_primitive_build import validate_primitive

    value = primitive()
    value["method_code"] = "def list_commits(self, page, project):\n    return []\n"
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert any("self.page" in error for error in errors)
    value = primitive("gitlab/format_duration")
    value["method"] = "format_duration"
    value["capability"] = "Format duration as final answer text."
    value["method_code"] = "def format_duration(self, seconds):\n    return str(seconds)\n"
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert any("workflow-level formatting" in error for error in errors)
    value = primitive("gitlab/count_commits")
    value["method"] = "count_commits"
    value["method_code"] = "def count_commits(self, project):\n    return 3\n"
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert any("record aggregation" in error for error in errors)


def test_gate_allows_count_directly_reported_by_site_grid():
    value = primitive("gitlab/count_filtered_records")
    value["method"] = "count_filtered_records"
    value["capability"] = "Read the displayed record count from a filtered site grid."
    value["owns"] = ["Read the grid's displayed total record count from page text"]
    value["method_code"] = (
        "def count_filtered_records(self, text):\n"
        "    import re\n"
        "    return int(re.search(r'(\\d+) records found', text).group(1))\n"
    )
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert not any("record aggregation" in error for error in errors)


def test_gate_requires_typed_seconds_when_duration_text_is_exposed():
    value = primitive()
    value["output_contract"] = {
        "type": "object", "properties": {"duration_text": {"type": "string"}},
    }
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "duration_text requires typed duration_seconds in the output contract" in errors

    value["output_contract"]["properties"]["duration_seconds"] = {"type": "number"}
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "duration_text requires typed duration_seconds in the output contract" not in errors


def test_gate_rejects_hard_coded_deployment_origin():
    value = primitive()
    value["method_code"] = (
        "def list_commits(self, project):\n"
        "    return self.page.goto('http://source-deployment.invalid/projects/' + project)\n"
    )
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "method_code hard-codes a deployment origin; derive it from runtime context" in errors


def test_gate_requires_async_public_playwright_method():
    value = primitive()
    value["method_code"] = "def list_commits(self, project):\n    return []\n"
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "public method list_commits must be async def for async Playwright" in errors


def test_gate_rejects_relative_python_playwright_navigation():
    value = primitive()
    value["method_code"] = (
        "async def list_commits(self, project):\n"
        "    await self.page.goto('/projects/' + project)\n"
        "    return []\n"
    )
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert any("Playwright navigation/request uses a relative" in error for error in errors)


def test_gate_rejects_requests_only_raise_for_status_on_playwright_response():
    value = primitive()
    value["method_code"] = (
        "async def list_commits(self, project):\n"
        "    response = await self.page.request.get(project)\n"
        "    response.raise_for_status()\n"
        "    return []\n"
    )
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert any("APIResponse has no raise_for_status" in error for error in errors)


def test_gate_rejects_page_global_generic_close_control():
    value = primitive()
    value["method_code"] = (
        "async def list_commits(self, project):\n"
        "    await self.page.get_by_role('button', name='Close').first.click()\n"
        "    return []\n"
    )
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert any("page-global generic Close" in error for error in errors)


def test_consolidation_merge_cannot_drop_a_source_input_mode():
    coordinates = primitive("gitlab/routes/get_route_coordinates", "routes")
    coordinates["input_contract"] = {
        "origin": {"properties": {"latitude": {}, "longitude": {}}},
        "destination": {"properties": {"latitude": {}, "longitude": {}}},
    }
    text = primitive("gitlab/routes/get_route_text", "routes")
    text["input_contract"] = {"origin_query": "str", "destination_query": "str"}
    replacement = primitive("gitlab/routes/list_commits", "routes")
    replacement["input_contract"] = text["input_contract"]
    _, errors, _ = validate_consolidation(
        {"operations": [{
            "op": "MERGE", "sources": ["coords", "text"], "feature": "routes",
            "replacement": replacement, "reason": "merge",
        }]},
        site="gitlab", pool={"coords": coordinates, "text": text},
        workflows={"w1": WORKFLOWS[0]},
    )
    assert any("MERGE drops source input modes" in error for error in errors)


def test_contract_semantic_roles_avoid_site_specific_alias_tables():
    from webwright.skill_factory.audited_primitive_build import _contract_leaf_fields

    source = {"type": "object", "properties": {
        "source_name": {"type": "string", "semantic_role": "source"},
        "target_label": {"type": "string", "semantic_role": "target"},
        "execution_variant": {"type": "string", "semantic_role": "mode"},
    }}
    replacement = {"type": "object", "properties": {
        "source": {"type": "string"},
        "target": {"type": "string"},
        "mode": {"type": "string"},
    }}
    assert _contract_leaf_fields(source) == _contract_leaf_fields(replacement)


def test_gate_rejects_unsafe_or_underspecified_guarantees():
    value = primitive()
    value["guarantees"]["supports_absence_proof"] = True
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "absence proof requires complete acquisition" in errors

    value = primitive()
    value["guarantees"]["configuration"] = {
        "kind": "semantic_enum",
        "input_field": None,
        "supported_values": [],
        "coupled_site_parameters_hidden": True,
    }
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "semantic_enum configuration requires supported_values" in errors

    value = primitive()
    value["acceptance_checks"] = []
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "acceptance_checks must be non-empty strings" in errors

    value = primitive()
    value["input_contract"] = {
        "type": "object",
        "properties": {"backend": {"type": "string", "enum": ["a", "b"]}},
    }
    value["guarantees"]["configuration"] = {
        "kind": "semantic_enum", "input_field": "backend",
        "supported_values": ["a"], "coupled_site_parameters_hidden": True,
    }
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "guarantees supported_values must match the configured input enum" in errors


def test_evidence_gate_records_template_escape_equivalence():
    from webwright.skill_factory.audited_primitive_build import validate_primitive

    source = "x = page.evaluate(\"() => ({ {PLACEHOLDER} })\")\n" + "y = 'long evidence'\n" * 8
    source = source.replace("{ {PLACEHOLDER} }", "{{ name: 'Contact Us' }}")
    quote = source.replace("{{ name: 'Contact Us' }}", "{ name: 'Contact Us' }")
    value = primitive()
    value["source_evidence"] = [{"workflow_id": "w", "template_id": 1,
                                 "code_quote": quote, "explanation": "direct"}]
    errors = validate_primitive(
        value, site="gitlab", workflows={"w": {"template_id": 1, "code": source}}
    )
    assert not errors
    assert value["source_evidence"][0]["evidence_match_mode"] == "template_escape_equivalent"


def test_evidence_gate_accepts_model_added_quote_escaping():
    from webwright.skill_factory.audited_primitive_build import validate_primitive

    source = 'm = re.search(r\'name="token" value="([^\"]+)"\', html)\n' * 8
    quote = source.replace('"', '\\"')
    value = primitive()
    value["source_evidence"] = [{"workflow_id": "w", "template_id": 1,
                                 "code_quote": quote, "explanation": "direct"}]
    errors = validate_primitive(
        value, site="gitlab", workflows={"w": {"template_id": 1, "code": source}}
    )
    assert not errors
    assert value["source_evidence"][0]["evidence_match_mode"] == "template_escape_equivalent"


def test_typed_output_description_may_explain_page_text_source():
    value = primitive()
    value["output_contract"]["description"] = (
        "Typed records parsed from visible page text; raw page text is not returned."
    )
    assert not any(
        "raw/untyped" in error
        for error in validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    )


def test_full_build_saves_batch_and_consolidation_snapshots(tmp_path):
    calls = []

    def fake(system, user):
        calls.append(json.loads(user))
        if calls[-1].get("review_kind") == "primitive_boundary_quality":
            return {"verdicts": [{"operation_index": 0, "verdict": "PASS", "reason": "clean"}],
                    "rejection_verdicts": []}
        if "workflow" in calls[-1]:
            return extraction(calls[-1]["workflow"])
        if "batch" in calls[-1]:
            return {
                "operations": [{"op": "ADD", "replacement": primitive()}],
                "workflow_attribution": [
                    {"workflow_id": "w1", "decision": "CONTRIBUTED", "operation_indices": [0]},
                    {"workflow_id": "w2", "decision": "SKIP", "reason": "covered"},
                ],
                "candidate_attribution": [
                    {"candidate_id": "w1::list_commits", "decision": "ADD", "operation_index": 0},
                    {"candidate_id": "w2::list_commits", "decision": "COVERED",
                     "target_id": "gitlab/list_commits", "reason": "same operation"},
                ],
            }
        return {"operations": [{"op": "KEEP", "source": "gitlab/list_commits",
                                 "feature": "commits"}]}

    result = build_audited_site_library(
        site="gitlab", workflows=WORKFLOWS, output=tmp_path,
        batch_size=8, seed=3, llm_fn=fake,
        behavior_smoke_feedback={"list_commits": {"ok": True}},
    )
    assert result["batch_count"] == 1
    assert (tmp_path / "batches/batch_000/snapshot/primitive_pool.json").exists()
    assert (tmp_path / "pre_consolidation/primitive_pool.json").exists()
    assert (tmp_path / "consolidation/coverage.json").exists()
    consolidation_input = json.loads((tmp_path / "consolidation/input.json").read_text())
    assert consolidation_input["behavior_smoke_feedback"]["list_commits"]["ok"] is True
    index = json.loads((tmp_path / "final_candidate/index.json").read_text())
    assert index["approved"] is False
    assert index["primitives"][0]["feature"] == "commits"


def test_full_build_reaudits_previously_accepted_consolidation_with_current_validator(tmp_path):
    calls = []

    def initial_fake(system, user):
        value = json.loads(user)
        if value.get("review_kind") == "primitive_boundary_quality":
            return {"verdicts": [{
                "operation_index": 0, "verdict": "PASS", "reason": "clean",
            }], "rejection_verdicts": []}
        if "workflow" in value:
            return extraction(value["workflow"])
        if "batch" in value:
            return {
                "operations": [{"op": "ADD", "replacement": primitive()}],
                "workflow_attribution": [{
                    "workflow_id": "w1", "decision": "CONTRIBUTED",
                    "operation_indices": [0],
                }],
                "candidate_attribution": [{
                    "candidate_id": "w1::list_commits", "decision": "ADD",
                    "operation_index": 0,
                }],
            }
        return {"operations": [{
            "op": "KEEP", "source": "gitlab/list_commits", "feature": "commits",
        }]}

    build_audited_site_library(
        site="gitlab", workflows=[WORKFLOWS[0]], output=tmp_path,
        batch_size=4, seed=3, llm_fn=initial_fake,
    )
    invalid = {"operations": [{
        "op": "KEEP", "source": "gitlab/list_commits", "feature": "BadFeature",
    }]}
    (tmp_path / "consolidation/attempts.json").write_text(json.dumps([{
        "attempt": 1, "proposal": invalid, "errors": [],
    }]))
    (tmp_path / "consolidation/proposal.json").write_text(json.dumps(invalid))
    (tmp_path / "consolidation/validation.json").write_text(json.dumps({
        "accepted": True, "errors": [],
    }))

    def retry_fake(system, user):
        value = json.loads(user)
        calls.append(value)
        assert value["previous_rejected_proposal"] == invalid
        assert any("feature" in error for error in value["validation_feedback"])
        return {"operations": [{
            "op": "KEEP", "source": "gitlab/list_commits", "feature": "commits",
        }]}

    build_audited_site_library(
        site="gitlab", workflows=[WORKFLOWS[0]], output=tmp_path,
        batch_size=4, seed=3, llm_fn=retry_fake, max_attempts=3,
    )

    assert len(calls) == 1
    validation = json.loads((tmp_path / "consolidation/validation.json").read_text())
    assert validation["accepted"] is True


def test_parallel_initial_batches_share_no_incremental_pool_and_consolidate_once(tmp_path):
    workflows = [
        {"id": f"w{i}", "task_id": i, "template_id": i * 10, "code": SOURCE}
        for i in range(1, 5)
    ]
    batch_barrier = threading.Barrier(2)
    consolidation_inputs = []

    def fake(system, user):
        value = json.loads(user)
        if value.get("review_kind") == "primitive_boundary_quality":
            return {"verdicts": [
                {"operation_index": 0, "verdict": "PASS", "reason": "clean"}
            ], "rejection_verdicts": []}
        if "workflow" in value:
            return extraction(value["workflow"])
        if "batch" in value:
            # A sequential implementation times out here; both independent batches must enter.
            batch_barrier.wait(timeout=2)
            first, *rest = value["batch"]
            replacement = primitive()
            replacement["source_evidence"] = [{
                "workflow_id": first["id"], "template_id": first["template_id"],
                "code_quote": SOURCE, "explanation": "direct",
            }]
            return {
                "operations": [{"op": "ADD", "replacement": replacement}],
                "workflow_attribution": [
                    {"workflow_id": first["id"], "decision": "CONTRIBUTED",
                     "operation_indices": [0]},
                    *[{"workflow_id": row["id"], "decision": "SKIP", "reason": "covered"}
                      for row in rest],
                ],
                "candidate_attribution": [
                    {"candidate_id": f"{first['id']}::list_commits", "decision": "ADD",
                     "operation_index": 0},
                    *[{"candidate_id": f"{row['id']}::list_commits", "decision": "COVERED",
                       "target_id": "gitlab/list_commits", "reason": "same operation"}
                      for row in rest],
                ],
            }
        consolidation_inputs.append(value)
        keys = [row["candidate_key"] for row in value["primitive_pool"]]
        replacement = primitive("gitlab/commits/list_commits", "commits")
        replacement["source_evidence"] = [{
            "workflow_id": "w1", "template_id": 10,
            "code_quote": SOURCE, "explanation": "merged parallel candidates",
        }]
        return {"operations": [{"op": "MERGE", "sources": keys, "feature": "commits",
                                 "replacement": replacement, "reason": "deduplicate"}]}

    result = build_audited_site_library(
        site="gitlab", workflows=workflows, output=tmp_path,
        batch_size=2, seed=3, llm_fn=fake, max_workers=4,
    )

    assert result["batch_count"] == 2
    assert result["pre_consolidation_count"] == 2
    assert len(consolidation_inputs) == 1
    assert consolidation_inputs[0]["primitive_pool"][0]["candidate_key"] != (
        consolidation_inputs[0]["primitive_pool"][1]["candidate_key"]
    )
    for number in range(2):
        batch_input = json.loads(
            (tmp_path / f"batches/batch_{number:03d}/input.json").read_text()
        )
        assert batch_input["build_mode"] == "parallel_initial"
        assert batch_input["catalog_index"] == []
        assert batch_input["retrieved_primitives"] == []
        snapshot = json.loads(
            (tmp_path / f"batches/batch_{number:03d}/snapshot/primitive_pool.json").read_text()
        )
        assert len(snapshot) == 1
