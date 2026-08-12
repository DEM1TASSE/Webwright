import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
MODULE_PATH = ROOT / "evals/odysseys/site_primitives.py"
SPEC = importlib.util.spec_from_file_location("odysseys_site_primitives", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_load_segments_canonicalizes_sites_and_preserves_answer_only(tmp_path):
    path = tmp_path / "segments.json"
    path.write_text(json.dumps({"task": [
        {"segment_id": "S1", "site": "https://www.wikipedia.org/wiki/X",
         "goal": "extract cast", "rubric_ids": ["R1"],
         "required_fields": ["cast"]},
        {"segment_id": "S2", "site": None, "goal": "summarize",
         "rubric_ids": ["R2"]},
    ]}))
    segments = MODULE.load_segments(path, "task")
    assert segments[0].site == "wikipedia_org"
    assert segments[1].site is None


def test_google_maps_is_not_collapsed_into_google_search():
    assert MODULE.canonical_site("https://www.google.com/maps/dir/A/B") == "google_maps"
    assert MODULE.canonical_site("maps.google.com") == "google_maps"
    assert MODULE.canonical_site("https://www.google.com/search?q=x") == "google_com"


def test_duplicate_rubric_assignment_is_rejected():
    segments = [
        MODULE.SiteSubgoal("S1", "a_com", "one", rubric_ids=("R1",)),
        MODULE.SiteSubgoal("S2", "b_com", "two", rubric_ids=("R1",)),
    ]
    try:
        MODULE.validate_segments(segments)
    except ValueError as exc:
        assert "multiple segments" in str(exc)
    else:
        raise AssertionError("duplicate rubric must fail")


def test_site_segments_are_independently_routed(tmp_path, monkeypatch):
    library = tmp_path / "library"
    for site in ("a_com", "b_com"):
        index = library / site / "final_candidate" / "index.json"
        index.parent.mkdir(parents=True)
        index.write_text(json.dumps({"site": site, "status": "candidate", "primitives": []}))

    calls = []
    import webwright.skill_factory.audited_primitive_retrieve as retrieve

    monkeypatch.setattr(retrieve, "draft_scratch_plan", lambda goal, site, plan_fn=None: {
        "site": site, "task": goal, "steps": [{"id": "S1", "action": goal}],
    })
    monkeypatch.setattr(retrieve, "retrieve_audited_primitives",
                        lambda goal, root, site, scratch_plan, decide_fn=None:
                        calls.append((site, goal)) or type("R", (), {
                            "decision": "skip", "reason": "none", "sources": [],
                            "scratch_plan": scratch_plan, "primitives": [],
                        })())
    monkeypatch.setattr(retrieve, "render_audited_primitive_hint", lambda result, include_code: "")
    monkeypatch.setattr(retrieve, "write_audited_retrieval", lambda *args, **kwargs: None)

    segments = [
        MODULE.SiteSubgoal("S1", "a_com", "goal a", rubric_ids=("R1",)),
        MODULE.SiteSubgoal("S2", "b_com", "goal b", rubric_ids=("R2",)),
        MODULE.SiteSubgoal("S3", None, "summarize", rubric_ids=("R3",)),
    ]
    results = MODULE.route_site_segments(segments, library, tmp_path / "records")
    assert calls == [("a_com", "goal a"), ("b_com", "goal b")]
    assert results[2].reason.startswith("answer-only")


def test_missing_site_library_skips_without_cross_site_fallback(tmp_path):
    segment = MODULE.SiteSubgoal("S1", "missing_com", "goal", rubric_ids=("R1",))
    result = MODULE.route_site_segments(
        [segment], tmp_path / "library", tmp_path / "records",
        plan_fn=lambda goal, site: {"steps": [{"id": "S1", "action": goal}]},
    )[0]
    assert result.decision == "skip"
    assert result.primitive_sources == []
    assert "missing_com" in result.reason
