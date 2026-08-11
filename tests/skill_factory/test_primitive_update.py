import json

from webwright.skill_factory.primitive_catalog import Primitive, PrimitiveCatalog
from webwright.skill_factory.primitive_update import (
    PrimitiveOperation,
    apply_updates,
    propose_updates,
    verify_operations_evidence,
)


GOLD = {"w1", "w2", "w3"}


def _op(op, name="reviews", **kw):
    values = dict(
        op=op,
        primitive_id=f"admin/{name}",
        capability=f"{name} capability",
        entrypoint=name,
        candidate_code=f"def {name}(page):\n    return page\n",
        source_templates=[1, 2],
        source_workflows=["w1", "w2"],
    )
    values.update(kw)
    return PrimitiveOperation(**values)


def _seed(cat, name="reviews"):
    p = _op("ADD", name)
    result = apply_updates(cat, [p], gold_workflows=GOLD)
    assert result.applied
    return cat.get(f"admin/{name}")


def test_add_and_no_change(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    result = apply_updates(
        cat,
        [_op("ADD"), PrimitiveOperation(op="NO_CHANGE", reason="unrelated pages")],
        gold_workflows=GOLD,
    )
    assert [x["op"] for x in result.applied] == ["ADD", "NO_CHANGE"]
    assert cat.get("admin/reviews") is not None


def test_add_accepts_one_gold_source_as_single_source(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    result = apply_updates(
        cat,
        [_op("ADD", source_templates=[1], source_workflows=["w1"])],
        gold_workflows=GOLD,
    )
    assert result.applied
    assert cat.get("admin/reviews").grade == "single_source"


def test_add_with_two_templates_is_shared(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    result = apply_updates(cat, [_op("ADD")], gold_workflows=GOLD)
    assert result.applied
    assert cat.get("admin/reviews").grade == "shared"


def test_modify_proposal_unions_existing_and_new_provenance(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    existing = _op(
        "ADD", source_templates=[1], source_workflows=["w1"],
        source_evidence=[{"workflow_id": "w1", "template_id": 1,
                          "code_quote": "old evidence", "explanation": "old"}],
    )
    assert apply_updates(cat, [existing], gold_workflows=GOLD).applied
    operations = propose_updates(
        site="admin",
        new_workflow={"id": "w2", "template_id": 2, "code": "new evidence"},
        peer_workflows=[],
        catalog=cat,
        llm_fn=lambda *_: {"operations": [{
            "op": "MODIFY", "primitive_id": "admin/reviews",
            "capability": "reviews capability", "entrypoint": "reviews",
            "candidate_code": "def reviews(page):\n    return page\n",
            "source_templates": [2], "source_workflows": ["w2"],
            "source_evidence": [{"workflow_id": "w2", "template_id": 2,
                                  "code_quote": "new evidence", "explanation": "new"}],
        }]},
    )
    assert operations[0].source_templates == [1, 2]
    assert operations[0].source_workflows == ["w1", "w2"]
    assert {x["workflow_id"] for x in operations[0].source_evidence} == {"w1", "w2"}


def test_modify_replaces_active_content_but_invalid_modify_keeps_old(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    old = _seed(cat)
    changed = _op(
        "MODIFY",
        candidate_code="def reviews(page):\n    return page.locator('.next')\n",
    )
    assert apply_updates(cat, [changed], gold_workflows=GOLD).applied
    current = cat.get("admin/reviews")
    assert current.content_hash != old.content_hash

    invalid = _op("MODIFY", candidate_code="not valid python :")
    result = apply_updates(cat, [invalid], gold_workflows=GOLD)
    assert result.rejected
    assert cat.get("admin/reviews").content_hash == current.content_hash


def test_split_is_not_part_of_minimal_incremental_protocol(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    _seed(cat, "coarse")
    replacements = [
        {
            "primitive_id": "admin/open_product",
            "capability": "open product",
            "entrypoint": "open_product",
            "candidate_code": "def open_product(page):\n    return page\n",
            "source_templates": [1, 2],
            "source_workflows": ["w1", "w2"],
        },
        {
            "primitive_id": "admin/list_reviews",
            "capability": "list reviews",
            "entrypoint": "list_reviews",
            "candidate_code": "def list_reviews(page):\n    return []\n",
            "source_templates": [2, 3],
            "source_workflows": ["w2", "w3"],
        },
    ]
    result = apply_updates(
        cat,
        [PrimitiveOperation(op="SPLIT", primitive_id="admin/coarse",
                            replacements=replacements)],
        gold_workflows=GOLD,
    )
    assert not result.applied
    assert result.rejected[0]["error"] == "unknown operation 'SPLIT'"
    assert cat.get("admin/coarse") is not None


def test_archive_is_not_part_of_minimal_incremental_protocol(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    _seed(cat, "old")
    review = tmp_path / "review.jsonl"
    result = apply_updates(
        cat,
        [
            _op("MODIFY", "old", confidence=0.2),
            PrimitiveOperation(op="ARCHIVE", primitive_id="admin/old"),
        ],
        gold_workflows=GOLD,
        review_path=review,
    )
    assert result.reviewed and not result.applied
    assert result.rejected[-1]["error"] == "unknown operation 'ARCHIVE'"
    assert json.loads(review.read_text())["primitive_id"] == "admin/old"


def test_proposer_parses_known_fields_only(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    operations = propose_updates(
        site="admin",
        new_workflow={"id": "w2", "code": "..."},
        peer_workflows=[{"id": "w1", "code": "..."}],
        catalog=cat,
        llm_fn=lambda system, user: {
            "operations": [{"op": "NO_CHANGE", "reason": "none", "ignored": 3}]
        },
    )
    assert operations == [PrimitiveOperation(op="NO_CHANGE", reason="none")]


def test_proposer_skips_malformed_operation_without_op(tmp_path):
    operations = propose_updates(
        site="admin",
        new_workflow={"id": "w2", "code": "..."},
        peer_workflows=[{"id": "w1", "code": "..."}],
        catalog=PrimitiveCatalog(tmp_path, "admin"),
        llm_fn=lambda system, user: {
            "operations": [
                {"reason": "missing operation kind"},
                {"op": "NO_CHANGE", "reason": "none"},
            ]
        },
    )
    assert operations == [PrimitiveOperation(op="NO_CHANGE", reason="none")]


def test_proposer_adapts_nested_candidate_and_derives_cited_provenance(tmp_path):
    operations = propose_updates(
        site="shopping",
        new_workflow={"id": "task2_t20", "template_id": 20, "code": "..."},
        peer_workflows=[{"id": "task1_t10", "template_id": 10, "code": "..."}],
        catalog=PrimitiveCatalog(tmp_path, "shopping"),
        llm_fn=lambda system, user: {
            "operations": [{
                "op": "ADD",
                "candidate": {
                    "name": "get_reviews",
                    "summary": "Get typed product reviews.",
                    "entrypoint": "get_reviews",
                    "code": "def get_reviews(page):\n    return []\n",
                },
                "evidence": [
                    "task1_t10 parses reviews",
                    "task2_t20 parses reviews",
                ],
            }]
        },
    )
    assert operations == [PrimitiveOperation(
        op="ADD",
        primitive_id="shopping/get_reviews",
        capability="Get typed product reviews.",
        entrypoint="get_reviews",
        candidate_code="def get_reviews(page):\n    return []\n",
        source_templates=[20, 10],
        source_workflows=["task2_t20", "task1_t10"],
    )]


def test_proposer_wraps_single_top_level_candidate(tmp_path):
    operations = propose_updates(
        site="shopping",
        new_workflow={"id": "task2_t20", "template_id": 20, "code": "..."},
        peer_workflows=[{"id": "task1_t10", "template_id": 10, "code": "..."}],
        catalog=PrimitiveCatalog(tmp_path, "shopping"),
        llm_fn=lambda system, user: {
            "name": "get_reviews",
            "description": "Get typed product reviews.",
            "sources": [
                {"workflow_id": "task1_t10", "evidence": "parses reviews"},
                {"workflow_id": "task2_t20", "evidence": "parses reviews"},
            ],
            "candidate": {
                "entrypoint": "get_reviews",
                "code": "def get_reviews(page):\n    return []\n",
            },
        },
    )
    assert len(operations) == 1
    assert operations[0].primitive_id == "shopping/get_reviews"
    assert set(operations[0].source_templates) == {10, 20}
    assert set(operations[0].source_workflows) == {"task1_t10", "task2_t20"}


def test_proposer_accepts_operation_as_op_alias(tmp_path):
    operations = propose_updates(
        site="admin",
        new_workflow={"id": "w2", "code": "..."},
        peer_workflows=[{"id": "w1", "code": "..."}],
        catalog=PrimitiveCatalog(tmp_path, "admin"),
        llm_fn=lambda system, user: {
            "operations": [{"operation": "NO_CHANGE", "reason": "none"}]
        },
    )
    assert operations == [PrimitiveOperation(op="NO_CHANGE", reason="none")]


def test_proposer_accepts_action_and_type_as_op_aliases(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    workflow = {"id": "w1", "template_id": 1, "code": "pass"}
    for alias in ("action", "type"):
        operations = propose_updates(
            site="admin", new_workflow=workflow, peer_workflows=[], catalog=cat,
            llm_fn=lambda *_, alias=alias: {
                "operations": [{alias: "NO_CHANGE", "reason": alias}]
            },
        )
        assert operations == [PrimitiveOperation(op="NO_CHANGE", reason=alias)]


def test_verified_evidence_accepts_real_spans_from_workflows(tmp_path):
    quote1 = "def parse_reviews(html):\n    rows = html.split('review-row')\n    return [row.strip() for row in rows if row.strip()]"
    quote2 = "def parse_reviews(text):\n    items = text.split('review-row')\n    return [item.strip() for item in items if item.strip()]"
    workflows = {
        "w1": {"id": "w1", "template_id": 1, "code": "import re\n\n" + quote1},
        "w2": {"id": "w2", "template_id": 2, "code": "import json\n\n" + quote2},
    }
    operation = _op("ADD", source_evidence=[
        {"workflow_id": "w1", "template_id": 1, "code_quote": quote1,
         "explanation": "This function directly splits and returns review rows."},
        {"workflow_id": "w2", "template_id": 2, "code_quote": quote2,
         "explanation": "This function directly splits and returns review rows."},
    ])
    verify_operations_evidence(
        [operation], workflows,
        llm_fn=lambda system, user: {"verdicts": [{
            "primitive_id": "admin/reviews",
            "supported_workflows": ["w1", "w2"],
            "reason": "both quotes directly parse review rows",
        }]},
    )
    result = apply_updates(
        PrimitiveCatalog(tmp_path, "admin"), [operation], gold_workflows=GOLD,
        workflow_evidence=workflows,
    )
    assert result.applied


def test_missing_or_semantically_rejected_evidence_blocks_promotion(tmp_path):
    workflows = {
        "w1": {"id": "w1", "template_id": 1, "code": "x = 'a' * 100"},
        "w2": {"id": "w2", "template_id": 2, "code": "y = 'b' * 100"},
    }
    missing = _op("ADD")
    verify_operations_evidence([missing], workflows, llm_fn=lambda *_: {})
    result = apply_updates(
        PrimitiveCatalog(tmp_path / "missing", "admin"), [missing],
        gold_workflows=GOLD, workflow_evidence=workflows,
    )
    assert not result.applied and "source_evidence" in result.rejected[0]["error"]

    quote1 = "def login(page):\n    page.goto('/login')\n    page.fill('username', 'admin')\n    page.click('submit-button')"
    quote2 = "def login(page):\n    page.goto('/login')\n    page.fill('username', 'admin')\n    page.click('submit-button')"
    workflows["w1"]["code"] = quote1
    workflows["w2"]["code"] = quote2
    rejected = _op("ADD", capability="parse order totals", source_evidence=[
        {"workflow_id": "w1", "template_id": 1, "code_quote": quote1,
         "explanation": "This is generic login code and not order parsing."},
        {"workflow_id": "w2", "template_id": 2, "code_quote": quote2,
         "explanation": "This is generic login code and not order parsing."},
    ])
    verify_operations_evidence(
        [rejected], workflows,
        llm_fn=lambda *_: {"verdicts": [{
            "primitive_id": "admin/reviews", "supported_workflows": [],
            "reason": "the quotes only implement login",
        }]},
    )
    result = apply_updates(
        PrimitiveCatalog(tmp_path / "semantic", "admin"), [rejected],
        gold_workflows=GOLD, workflow_evidence=workflows,
    )
    assert not result.applied and "independent evidence" in result.rejected[0]["error"]


def test_independent_judge_blocks_redundant_add(tmp_path):
    quote1 = "def route(coords):\n    url = '/route/' + ';'.join(coords)\n    return request_json(url)['routes'][0]['duration']"
    quote2 = "def route(points):\n    url = '/route/' + ';'.join(points)\n    return request_json(url)['routes'][0]['duration']"
    workflows = {
        "w1": {"id": "w1", "template_id": 1, "code": quote1},
        "w2": {"id": "w2", "template_id": 2, "code": quote2},
    }
    operation = _op("ADD", name="route_duration", source_evidence=[
        {"workflow_id": "w1", "template_id": 1, "code_quote": quote1,
         "explanation": "Directly requests a route and returns its duration."},
        {"workflow_id": "w2", "template_id": 2, "code_quote": quote2,
         "explanation": "Directly requests a route and returns its duration."},
    ])
    verify_operations_evidence(
        [operation], workflows, active_primitives=[_seed(PrimitiveCatalog(tmp_path, "admin"))],
        llm_fn=lambda *_: {"verdicts": [{
            "primitive_id": "admin/route_duration",
            "supported_workflows": ["w1", "w2"],
            "redundant_with": "admin/reviews",
            "reason": "the active primitive already covers route retrieval",
        }]},
    )
    assert operation.evidence_verified is False
    assert "redundant with admin/reviews" in operation.evidence_verification_reason
