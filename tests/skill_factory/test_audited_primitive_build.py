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
            "configuration": {"kind": "none", "supported_values": [],
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
        "method_code": "def list_commits(self, project):\n    return []\n",
        "owns": ["GitLab commit selectors and parsing"],
        "does_not_own": ["task filtering and answer formatting"],
        "input_contract": {"project": "str"},
        "output_contract": {"type": "list[CommitRecord]", "fields": {"title": "str"}},
        "requires": ["authenticated_session"], "provides": ["typed_commit_records"],
        "supported_patterns": [],
        "guarantees": {
            "collection_scope": "page", "completeness": "partial",
            "supports_absence_proof": False,
            "configuration": {"kind": "none", "supported_values": [],
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
    replacement["method_code"] = "def list_commits(self, project):\n    return [{'title': project}]\n"
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
                "latitude": {"type": "number"}, "longitude": {"type": "number"},
            }},
        }},
    }
    extracted = extraction(WORKFLOWS[0])
    extracted["candidates"][0]["output_contract"] = {
        "type": "array", "items": {"type": "object", "properties": {
            "lat": {"type": "string"}, "lon": {"type": "string"},
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


def test_semantic_output_fields_normalize_site_record_naming_without_hiding_real_fields():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    candidate = {"properties": {"orders": {"items": {"properties": {
        "display_date": {}, "display_order_total": {}, "status": {}, "detail_url": {},
    }}}}}
    target = {"properties": {"orders": {"items": {"properties": {
        "order_date_display": {}, "order_total_display": {}, "status_display": {},
        "order_detail_url": {},
    }}}}}
    assert _semantic_output_fields(candidate) <= _semantic_output_fields(target)
    assert "nickname" in _semantic_output_fields({"properties": {"nickname": {}}})


def test_semantic_output_fields_normalize_magento_graphql_flattening():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    extracted = {"fields": {"records": {"items": {"fields": {
        "product_url": {}, "minimum_final_price_value": {}, "currency": {},
    }}}}}
    generated = {"properties": {"products": {"items": {"properties": {
        "url": {}, "price_range": {"properties": {"minimum_price": {
            "properties": {"final_price": {"properties": {
                "value": {}, "currency": {},
            }}},
        }}},
    }}}}}
    assert _semantic_output_fields(extracted) <= _semantic_output_fields(generated)


def test_semantic_output_fields_ignore_compact_container_names_and_normalize_review_id():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    many = {"records": {"items": {"fields": {"id": {}, "detail": {}}}}}
    one = {"properties": {"record": {"properties": {
        "review_id": {}, "review_text": {},
    }}}}
    assert _semantic_output_fields(many) == _semantic_output_fields(one) == {"id", "detail"}


def test_semantic_output_fields_normalize_auth_facts_and_hide_private_token_values():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    extracted = {"properties": {
        "authenticated": {"type": "boolean"},
        "dashboard_url": {"type": "string"},
        "form_key": {"type": "string"},
    }}
    existing = {"properties": {
        "is_authenticated": {"type": "boolean"},
        "final_url": {"type": "string"},
        "form_key_present": {"type": "boolean"},
    }}

    assert _semantic_output_fields(extracted) <= _semantic_output_fields(existing)
    assert "form_key" not in _semantic_output_fields(extracted)


def test_semantic_output_fields_compare_flat_and_wrapped_review_contracts():
    from webwright.skill_factory.audited_primitive_build import _semantic_output_fields

    extracted = {"properties": {"review": {"properties": {
        "review_id": {}, "product_name": {}, "nickname": {}, "summary": {},
        "review_text": {},
    }}}}
    richer_flat = {"properties": {
        "review_id": {}, "product": {}, "nickname": {}, "title": {}, "detail": {},
        "rating": {},
    }}

    assert _semantic_output_fields(extracted) <= _semantic_output_fields(richer_flat)


def test_covered_auth_candidate_can_drop_private_token_but_not_semantic_facts():
    target = primitive()
    target["primitive_id"] = "shopping_admin/login_admin"
    target["method"] = "login_admin"
    target["output_contract"] = {"type": "object", "properties": {
        "is_authenticated": {"type": "boolean"},
        "final_url": {"type": "string"},
        "form_key_present": {"type": "boolean"},
    }}
    extracted = extraction(WORKFLOWS[0])
    extracted["candidates"][0]["output_contract"] = {
        "authenticated": "boolean", "dashboard_url": "string", "form_key": "string",
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


def test_primitive_rejects_opaque_viewbox_string_contract():
    from webwright.skill_factory.audited_primitive_build import validate_primitive

    candidate = primitive()
    candidate["input_contract"] = {
        "type": "object", "properties": {
            "viewbox": {"type": "string"},
        },
    }
    errors = validate_primitive(
        candidate, site="gitlab", workflows={"w1": WORKFLOWS[0]},
    )
    assert "viewbox input must be a typed bounds object, not a serialized string" in errors


def test_merge_and_split_generate_complete_classified_replacements():
    second = primitive("gitlab/get_commits")
    second["method"] = "get_commits"
    second["method_code"] = "def get_commits(self, project):\n    return []\n"
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
    b["method_code"] = "def get_commit(self, sha):\n    return {'sha': sha}\n"
    b["input_contract"] = {"sha": "str"}
    final, errors, _ = validate_consolidation(
        {"operations": [{"op": "SPLIT", "source": "gitlab/list_commits",
                         "replacements": [a, b]}]},
        site="gitlab", pool={"gitlab/list_commits": primitive()},
        workflows={x["id"]: x for x in WORKFLOWS},
    )
    assert not errors and {x["method"] for x in final} == {"list_commits", "get_commit"}


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


def test_gate_rejects_unsafe_or_underspecified_guarantees():
    value = primitive()
    value["guarantees"]["supports_absence_proof"] = True
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "absence proof requires complete acquisition" in errors

    value = primitive()
    value["guarantees"]["configuration"] = {
        "kind": "semantic_enum",
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
    errors = validate_primitive(value, site="gitlab", workflows={"w1": WORKFLOWS[0]})
    assert "public configuration enum requires semantic_enum guarantees" in errors
    assert "guarantees supported_values must match public configuration enum" in errors


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
    )
    assert result["batch_count"] == 1
    assert (tmp_path / "batches/batch_000/snapshot/primitive_pool.json").exists()
    assert (tmp_path / "pre_consolidation/primitive_pool.json").exists()
    assert (tmp_path / "consolidation/coverage.json").exists()
    index = json.loads((tmp_path / "final_candidate/index.json").read_text())
    assert index["approved"] is False
    assert index["primitives"][0]["feature"] == "commits"


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
