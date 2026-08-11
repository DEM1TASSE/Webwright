import importlib.util
from pathlib import Path


PATH = Path(__file__).parents[2] / "evals" / "webvoyager" / "validate_split.py"
SPEC = importlib.util.spec_from_file_location("webvoyager_split", PATH)
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)


def task(task_id, site="GitHub"):
    return {"task_id": task_id, "web_name": site, "task": "x", "website": "https://github.com/"}


def test_split_reports_cross_template_capability_overlap():
    manifest = {"sites": {"GitHub": {
        "source": [{"task_id": "a", "family_id": "search",
                    "capabilities": ["open_repo"]}],
        "heldout": [{"task_id": "b", "family_id": "release",
                     "capabilities": ["open_repo"]}],
    }}}
    result = S.validate(manifest, {"a": task("a"), "b": task("b")})
    assert result["valid"] is True
    assert result["summary"]["sites"]["GitHub"]["family_overlap"] == []
    assert result["summary"]["sites"]["GitHub"]["capability_overlap"] == ["open_repo"]


def test_split_rejects_leakage_and_wrong_site():
    manifest = {"sites": {"GitHub": {
        "source": [{"task_id": "a", "family_id": "search"}],
        "heldout": [{"task_id": "a", "family_id": "release"},
                    {"task_id": "b", "family_id": "release"}],
    }}}
    result = S.validate(manifest, {"a": task("a"), "b": task("b", "ArXiv")})
    assert result["valid"] is False
    assert any("duplicate task_id" in error for error in result["errors"])
    assert any("dataset site" in error for error in result["errors"])
