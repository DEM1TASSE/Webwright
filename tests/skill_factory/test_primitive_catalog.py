import json

import pytest

from webwright.skill_factory.primitive_catalog import (
    Primitive,
    PrimitiveCatalog,
    render_site_primitive_class,
    validate_primitive,
)


def _primitive(name="open_repo", code=None):
    code = code or (
        "def open_repo(page, repo):\n"
        "    return _normalize(repo)\n\n"
        "def _normalize(repo):\n"
        "    return repo.strip()\n"
    )
    return Primitive(
        primitive_id=f"gitlab/{name}",
        site="gitlab",
        capability="Open a GitLab repository.",
        entrypoint=name,
        code=code,
        signature={"inputs": {"repo": "string"}, "output_schema": {"type": "string"}},
        requires=["authenticated_session"],
        provides=["repo_context"],
        source_templates=[322, 329],
    )


def test_catalog_exposes_one_site_primitive_class(tmp_path):
    catalog = PrimitiveCatalog(tmp_path, "gitlab")
    primitive = catalog.upsert(_primitive())

    site_class = catalog.as_site_class()

    assert site_class.site == "gitlab"
    assert site_class.get_method("gitlab/open_repo") == primitive
    assert site_class.method_metadata()[0]["method_name"] == "open_repo"
    assert "code" not in site_class.method_metadata()[0]
    generated = catalog.class_path.read_text()
    assert "class GitLabPrimitives:" in generated
    assert "def open_repo(" in generated
    compile(generated, str(catalog.class_path), "exec")


def test_site_class_namespaces_private_helpers():
    first = _primitive("open_repo")
    second = Primitive(
        primitive_id="gitlab/find_repo",
        site="gitlab",
        capability="Find a GitLab repository.",
        entrypoint="find_repo",
        code=(
            "def find_repo(repo):\n"
            "    return _normalize(repo)\n\n"
            "def _normalize(repo):\n"
            "    return repo.lower()\n"
        ),
    )
    generated = render_site_primitive_class("gitlab", [first, second])
    namespace = {}
    exec(generated, namespace)
    site_class = namespace["GitLabPrimitives"]
    assert site_class.open_repo(None, " A ") == "A"
    assert site_class.find_repo(" A ") == " a "
    assert "_open_repo__normalize" in generated
    assert "_find_repo__normalize" in generated


def test_catalog_round_trip_and_hash(tmp_path):
    catalog = PrimitiveCatalog(tmp_path, "gitlab")
    primitive = catalog.upsert(_primitive())

    loaded = catalog.get("gitlab/open_repo")
    assert loaded is not None
    assert loaded.code == primitive.code
    assert loaded.content_hash == primitive.content_hash
    assert loaded.requires == ["authenticated_session"]

    raw = json.loads(catalog.catalog_path.read_text())
    assert raw["schema_version"] == 1
    assert raw["primitives"][0]["code_path"] == "code/open_repo.py"


def test_upsert_replaces_active_implementation_without_versions(tmp_path):
    catalog = PrimitiveCatalog(tmp_path, "gitlab")
    old = catalog.upsert(_primitive())
    new = catalog.upsert(_primitive(code="def open_repo(page, repo):\n    return repo.lower()\n"))

    assert old.content_hash != new.content_hash
    assert len(catalog.list()) == 1
    assert catalog.get("gitlab/open_repo").content_hash == new.content_hash


def test_archive_removes_from_active_retrieval(tmp_path):
    catalog = PrimitiveCatalog(tmp_path, "gitlab")
    catalog.upsert(_primitive())

    assert catalog.archive("gitlab/open_repo")
    assert catalog.get("gitlab/open_repo") is None
    archived = catalog.get("gitlab/open_repo", include_archived=True)
    assert archived is not None
    assert archived.status == "archived"


def test_requires_provides_are_metadata_not_code_dependencies():
    primitive = _primitive()
    validate_primitive(primitive, other_entrypoints={"login"})
    assert "authenticated_session" in primitive.requires
    assert "login" not in primitive.code


def test_rejects_cross_catalog_call():
    primitive = _primitive(
        code="def open_repo(page, repo):\n    login(page)\n    return repo\n"
    )
    with pytest.raises(ValueError, match="other catalog primitives"):
        validate_primitive(primitive, other_entrypoints={"login"})


def test_rejects_missing_entrypoint_and_catalog_import():
    with pytest.raises(ValueError, match="not defined"):
        validate_primitive(_primitive(code="def other():\n    pass\n"))

    bad = _primitive(
        code="from webwright.skill_factory.primitive_catalog import PrimitiveCatalog\n\n"
        "def open_repo(page, repo):\n    return repo\n"
    )
    with pytest.raises(ValueError, match="may not import"):
        validate_primitive(bad)


def test_rejects_unsafe_site_and_name(tmp_path):
    with pytest.raises(ValueError):
        PrimitiveCatalog(tmp_path, "../gitlab")
    with pytest.raises(ValueError):
        validate_primitive(
            Primitive(
                primitive_id="gitlab/../oops",
                site="gitlab",
                capability="bad",
                entrypoint="oops",
                code="def oops():\n    pass\n",
            )
        )
