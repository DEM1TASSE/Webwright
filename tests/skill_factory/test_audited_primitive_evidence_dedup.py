from webwright.skill_factory.audited_primitive_build import deduplicate_source_evidence


def test_deduplicates_workflow_evidence_in_merge_and_split():
    raw = {"operations": [
        {"replacement": {"source_evidence": [
            {"workflow_id": "a", "explanation": "first"},
            {"workflow_id": "a", "explanation": "duplicate"},
            {"workflow_id": "b", "explanation": "other"},
        ]}},
        {"replacements": [{"source_evidence": [
            {"workflow_id": "c"}, {"workflow_id": "c"},
        ]}]},
    ]}
    result = deduplicate_source_evidence(raw)
    assert [row["workflow_id"] for row in
            result["operations"][0]["replacement"]["source_evidence"]] == ["a", "b"]
    assert len(result["operations"][1]["replacements"][0]["source_evidence"]) == 1
