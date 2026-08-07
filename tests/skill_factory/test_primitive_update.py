import json

from webwright.skill_factory.primitive_catalog import Primitive, PrimitiveCatalog
from webwright.skill_factory.primitive_update import (
    PrimitiveOperation,
    apply_updates,
    propose_updates,
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


def test_add_requires_cross_template_gold_evidence(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "admin")
    result = apply_updates(
        cat,
        [_op("ADD", source_templates=[1], source_workflows=["w1"])],
        gold_workflows=GOLD,
    )
    assert not result.applied and "two source templates" in result.rejected[0]["error"]


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


def test_split_replaces_coarse_active_surface(tmp_path):
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
    assert result.applied
    assert cat.get("admin/coarse") is None
    assert cat.get("admin/coarse", include_archived=True).status == "archived"
    assert {p.primitive_id for p in cat.list()} == {
        "admin/open_product", "admin/list_reviews"
    }


def test_archive_and_uncertain_review_do_not_block(tmp_path):
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
    assert result.reviewed and result.applied[-1]["op"] == "ARCHIVE"
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
