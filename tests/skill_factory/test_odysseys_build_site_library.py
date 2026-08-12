import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
ODYSSEYS = ROOT / "evals/odysseys"
sys.path.insert(0, str(ODYSSEYS))
SPEC = importlib.util.spec_from_file_location(
    "odysseys_build_site_library", ODYSSEYS / "build_site_library.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_only_rubric_successful_scratch_segments_are_admitted(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "final_script.py").write_text("async def main(page):\n    pass\n")
    code_a = tmp_path / "a.py"
    code_b = tmp_path / "b.py"
    code_a.write_text("async def lookup_a(page):\n    pass\n")
    code_b.write_text("async def lookup_b(page):\n    pass\n")
    segments = tmp_path / "segments.json"
    segments.write_text(json.dumps({"task": [
        {"segment_id": "A", "site": "a.com", "template_id": "a.lookup",
         "goal": "lookup a", "rubric_ids": ["R1"]},
        {"segment_id": "B", "site": "b.com", "template_id": "b.lookup",
         "goal": "lookup b", "rubric_ids": ["R2"]},
        {"segment_id": "C", "site": None, "template_id": "answer.combine",
         "goal": "summarize", "rubric_ids": ["R3"]},
    ]}))
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"sources": [{
        "task_id": "task", "mode": "scratch", "run_dir": str(run),
        "segments": str(segments), "segment_code": {"A": str(code_a), "B": str(code_b)},
    }]}))
    judge = tmp_path / "judge.json"
    judge.write_text(json.dumps({"tasks": [{"task_id": "task", "rubric_scores": {
        "R1": 1, "R2": 0, "R3": 1,
    }}]}))
    result = MODULE.admitted_workflows(manifest, judge)
    assert list(result) == ["a_com"]
    assert result["a_com"][0]["template_id"] == "a.lookup"


def test_primitive_mode_cannot_be_source_evidence(tmp_path):
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"sources": [{
        "task_id": "task", "mode": "primitive", "run_dir": "/irrelevant",
        "segments": "/irrelevant",
    }]}))
    judge = tmp_path / "judge.json"
    judge.write_text(json.dumps({"tasks": []}))
    try:
        MODULE.admitted_workflows(manifest, judge)
    except ValueError as exc:
        assert "cannot be source evidence" in str(exc)
    else:
        raise AssertionError("primitive source must fail")


def test_workspace_level_source_script_is_accepted(tmp_path):
    workspace = tmp_path / "workspace"
    run = workspace / "final_runs" / "run_1"
    run.mkdir(parents=True)
    (workspace / "final_script.py").write_text("print('executed')\n")
    code = tmp_path / "segment.py"
    code.write_text("print('site segment')\n")
    segments = tmp_path / "segments.json"
    segments.write_text(json.dumps({"task": [{
        "segment_id": "S1", "site": "a.com", "template_id": "a.lookup",
        "goal": "lookup a", "rubric_ids": ["R1"],
    }]}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{
        "task_id": "task", "mode": "scratch", "run_dir": str(run),
        "segments": str(segments), "segment_code": {"S1": str(code)},
    }]}))
    judge = tmp_path / "judge.json"
    judge.write_text(json.dumps({"tasks": [{
        "task_id": "task", "rubric_scores": {"R1": 1},
    }]}))
    assert list(MODULE.admitted_workflows(manifest, judge)) == ["a_com"]
