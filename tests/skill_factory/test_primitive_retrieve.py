import json

from webwright.skill_factory.primitive_catalog import Primitive, PrimitiveCatalog
from webwright.skill_factory.primitive_retrieve import (
    decide_primitive_metadata,
    extract_primitive_usage,
    read_declared_coverage,
    read_declared_usage,
    render_primitive_hint,
    retrieve_primitives,
    write_retrieval_record,
)


def _p(name, capability, *, requires=(), provides=()):
    return Primitive(
        primitive_id=f"gitlab/{name}",
        site="gitlab",
        capability=capability,
        entrypoint=name,
        code=f"def {name}(page):\n    return page\n",
        requires=list(requires),
        provides=list(provides),
    )


def test_keyword_retrieval_is_site_scoped_and_bounded(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "gitlab")
    cat.upsert(_p("search_projects", "search GitLab projects"))
    cat.upsert(_p("list_commits", "list repository commits"))
    result = retrieve_primitives(
        "list commits in this repository", tmp_path, site="gitlab", max_primitives=1
    )
    assert result.primitive_ids == ["gitlab/list_commits"]


def test_unrelated_same_site_task_returns_empty_retrieval(tmp_path):
    PrimitiveCatalog(tmp_path, "gitlab").upsert(
        _p("list_commits", "list repository commits")
    )
    result = retrieve_primitives(
        "change my notification email preference", tmp_path, site="gitlab"
    )
    assert result.primitive_ids == [] and result.reason == "no relevant site primitive"


def test_metadata_decider_never_receives_primitive_code(tmp_path):
    primitive = _p("list_commits", "list repository commits")
    primitive.code = (
        "def list_commits(page):\n"
        "    TOP_SECRET_IMPLEMENTATION = True\n"
        "    return page\n"
    )
    PrimitiveCatalog(tmp_path, "gitlab").upsert(primitive)
    captured = {}

    def decide(task, metadata):
        captured["metadata"] = metadata
        return {
            "decision": "use",
            "primitive_ids": ["gitlab/list_commits"],
            "reason": "direct match",
        }

    result = decide_primitive_metadata(
        "list commits", tmp_path, site="gitlab", decide_fn=decide
    )
    assert result.decision == "use"
    assert all("code" not in item for item in captured["metadata"])
    assert "TOP_SECRET_IMPLEMENTATION" not in repr(captured["metadata"])


def test_metadata_decider_rejects_unknown_ids_and_empty_use(tmp_path):
    PrimitiveCatalog(tmp_path, "gitlab").upsert(_p("list_commits", "list commits"))
    unknown = decide_primitive_metadata(
        "list commits", tmp_path, site="gitlab",
        decide_fn=lambda *_: {
            "decision": "use", "primitive_ids": ["gitlab/not_in_catalog"]
        },
    )
    empty = decide_primitive_metadata(
        "list commits", tmp_path, site="gitlab",
        decide_fn=lambda *_: {"decision": "adapt", "primitive_ids": []},
    )
    assert unknown.decision == "skip" and unknown.primitive_ids == []
    assert empty.decision == "skip" and empty.primitive_ids == []


def test_requires_adds_provider_and_orders_it_first(tmp_path):
    cat = PrimitiveCatalog(tmp_path, "gitlab")
    cat.upsert(_p("login", "authenticate user", provides=["authenticated_session"]))
    cat.upsert(_p(
        "open_repo", "open repository project",
        requires=["authenticated_session"], provides=["repo_context"],
    ))
    result = retrieve_primitives(
        "open repository project",
        tmp_path,
        site="gitlab",
        rank_fn=lambda task, ps: ["gitlab/open_repo"],
    )
    assert result.primitive_ids == ["gitlab/login", "gitlab/open_repo"]
    assert result.missing_requirements == []


def test_unresolved_requirement_is_reported_not_turned_into_code_dependency(tmp_path):
    PrimitiveCatalog(tmp_path, "gitlab").upsert(
        _p("open_repo", "open repository", requires=["authenticated_session"])
    )
    result = retrieve_primitives("open repository", tmp_path, site="gitlab")
    assert result.missing_requirements == ["authenticated_session"]


def test_hint_contains_code_vendoring_rule_and_provenance(tmp_path):
    p = _p("list_commits", "list commits")
    PrimitiveCatalog(tmp_path, "gitlab").upsert(p)
    result = retrieve_primitives("list commits", tmp_path, site="gitlab")
    hint = render_primitive_hint(result)
    assert p.code.strip() in hint
    assert f"signature: {json.dumps(p.signature)}" in hint
    assert "Do NOT import" in hint and "standalone workflow" in hint
    assert f"# primitive-source: {p.primitive_id} {p.content_hash}" in hint


def test_usage_markers_are_deduplicated():
    h = "sha256:" + "a" * 64
    code = f"# primitive-source: gitlab/login {h}\n# primitive-source: gitlab/login {h}\n"
    assert extract_primitive_usage(code) == [
        {"primitive_id": "gitlab/login", "content_hash": h}
    ]


def test_retrieval_record_distinguishes_offered_material_from_actual_usage(tmp_path):
    p = _p("list_commits", "list commits")
    PrimitiveCatalog(tmp_path, "gitlab").upsert(p)
    result = retrieve_primitives("list commits", tmp_path, site="gitlab")
    path = tmp_path / "run" / "primitive_retrieval.json"
    write_retrieval_record(path, result, task="list commits")
    saved = json.loads(path.read_text())
    assert saved["retrieved"] == [{"primitive_id": p.primitive_id, "content_hash": p.content_hash}]
    assert "used" not in saved


def test_declared_coverage_is_validated(tmp_path):
    path = tmp_path / "primitive_usage.json"
    path.write_text(json.dumps({
        "used": [],
        "coverage_assessment": {
            "covered": ["typed reviews"],
            "remaining": ["customer identity"],
            "sufficiency": "partial",
        },
    }))
    assert read_declared_coverage(path) == {
        "covered": ["typed reviews"],
        "remaining": ["customer identity"],
        "sufficiency": "partial",
    }
    path.write_text(json.dumps({
        "coverage_assessment": {
            "covered": "typed reviews",
            "remaining": [],
            "sufficiency": "mostly",
        },
    }))
    assert read_declared_coverage(path) is None


def test_declared_usage_is_defensive(tmp_path):
    path = tmp_path / "primitive_usage.json"
    path.write_text(json.dumps({"used": [
        {"primitive_id": "gitlab/login", "content_hash": "sha256:x"},
        {"bad": True},
    ]}))
    assert read_declared_usage(path) == [
        {"primitive_id": "gitlab/login", "content_hash": "sha256:x"}
    ]
