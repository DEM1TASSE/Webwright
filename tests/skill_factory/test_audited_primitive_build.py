import json

import pytest

from webwright.skill_factory.audited_primitive_build import (
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
    final, errors, _ = validate_consolidation(
        {"operations": [{"op": "SPLIT", "source": "gitlab/list_commits",
                         "replacements": [a, b]}]},
        site="gitlab", pool={"gitlab/list_commits": primitive()},
        workflows={x["id"]: x for x in WORKFLOWS},
    )
    assert not errors and {x["method"] for x in final} == {"list_commits", "get_commit"}


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
