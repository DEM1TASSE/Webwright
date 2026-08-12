"""Coverage measured from the pipeline's own records, with its blind spot stated."""
from __future__ import annotations

import json
from pathlib import Path

from skill_agent.coverage import compare_extractions, format_report, report


def _library(tmp_path: Path, extractions: dict, candidate_attribution: list,
             workflow_attribution: list) -> Path:
    library = tmp_path / "gitlab"
    for workflow_id, candidates in extractions.items():
        path = library / "extractions" / workflow_id / "extraction.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "decision": "CANDIDATES" if candidates else "SKIP",
            "candidates": [{"candidate_id": c} for c in candidates]}), encoding="utf-8")
    batch = library / "batches" / "batch_000"
    batch.mkdir(parents=True, exist_ok=True)
    (batch / "proposal.json").write_text(json.dumps({
        "operations": [], "candidate_attribution": candidate_attribution,
        "workflow_attribution": workflow_attribution}), encoding="utf-8")
    return library


def test_counts_kept_versus_demonstrated(tmp_path):
    library = _library(
        tmp_path,
        {"task1_t1": ["task1_t1::a", "task1_t1::b"], "task2_t2": ["task2_t2::c"]},
        [{"candidate_id": "task1_t1::a", "decision": "ADD"},
         {"candidate_id": "task1_t1::b", "decision": "COVERED"},
         {"candidate_id": "task2_t2::c", "decision": "REJECT", "reason": "evidence too weak"}],
        [{"workflow_id": "task1_t1", "decision": "CONTRIBUTED"},
         {"workflow_id": "task2_t2", "decision": "SKIP", "reason": "search evidence too weak"}])
    data = report(library)
    assert (data["demonstrated"], data["kept"]) == (3, 2)
    assert data["contributed_nothing"] == ["task2_t2"]
    rendered = format_report(data)
    assert "evidence too weak" in rendered
    assert "Blind spot" in rendered, "the blind spot must be stated, not hidden"


def test_a_workflow_that_extracted_nothing_is_distinguished_from_one_that_was_dropped(tmp_path):
    library = _library(tmp_path, {"task9_t9": []}, [],
                       [{"workflow_id": "task9_t9", "decision": "SKIP", "reason": "local git"}])
    data = report(library)
    assert data["workflows"][0]["extracted_nothing"] is True
    assert "extraction found nothing reusable" in format_report(data)


def test_comparing_runs_finds_what_one_extraction_missed(tmp_path):
    """The only signal that sees past extraction's own blind spot."""
    a = _library(tmp_path / "a", {"w1": ["w1::x"], "w2": ["w2::y"]}, [], [])
    b = _library(tmp_path / "b", {"w1": ["w1::x"], "w2": ["w2::y", "w2::z"]}, [], [])
    data = compare_extractions([a, b])
    assert data["unstable"] == ["w2"]
    assert [r["counts"] for r in data["workflows"]] == [[1, 1], [1, 2]]


def test_stable_runs_report_no_instability(tmp_path):
    a = _library(tmp_path / "a", {"w1": ["w1::x"]}, [], [])
    b = _library(tmp_path / "b", {"w1": ["w1::x"]}, [], [])
    assert compare_extractions([a, b])["unstable"] == []
