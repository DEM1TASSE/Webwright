import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2] / "evals" / "webvoyager"
PIPE_SPEC = importlib.util.spec_from_file_location("pipeline", ROOT / "pipeline.py")
PIPE = importlib.util.module_from_spec(PIPE_SPEC)
PIPE_SPEC.loader.exec_module(PIPE)
sys.modules["pipeline"] = PIPE
SPEC = importlib.util.spec_from_file_location("webvoyager_composite", ROOT / "composite_pipeline.py")
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


def test_build_composite_dataset_and_scope_validation(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text("".join(json.dumps(row) + "\n" for row in [
        {"id": "A--0", "ques": "first", "web": "https://a.test/", "web_name": "A"},
        {"id": "B--0", "ques": "second", "web": "https://b.test/", "web_name": "B"},
    ]))
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"bundles": [{
        "id": "bundle", "scope": "cross_site", "task_ids": ["A--0", "B--0"]
    }]}))
    output = tmp_path / "composites.jsonl"
    rows = C.build_dataset(tasks, spec, output)
    assert rows[0]["subtask_ids"] == ["A--0", "B--0"]
    assert "SUBTASK A--0" in rows[0]["ques"]
    assert "SUBTASK B--0" in rows[0]["ques"]


def test_named_evidence_and_summary():
    screenshots = ["/x/final_execution_1_github_15.png", "/x/other.png"]
    selected, mode = C.select_evidence(screenshots, "GitHub--15", 5)
    assert selected == [screenshots[0]]
    assert mode == "task_named"
    rows = [
        {"bundle_id": "b2", "scope": "cross_site", "bundle_size": 2,
         "predicted_label": 1},
        {"bundle_id": "b2", "scope": "cross_site", "bundle_size": 2,
         "predicted_label": 0},
    ]
    report = C.summarize(rows, baseline_accuracy=1.0)
    assert report["strata"][0]["micro_accuracy"] == 0.5
    assert report["strata"][0]["delta_from_single_baseline"] == -0.5
    assert report["bundle_results"]["b2"]["all_pass"] is False


def test_judgeable_run_accepts_subtask_answer_block(tmp_path):
    run = tmp_path / "workspace" / "final_runs" / "run_001"
    shots = run / "screenshots"
    shots.mkdir(parents=True)
    (shots / "final_execution_1_a_0.png").write_bytes(b"png")
    (run / "final_script_log.txt").write_text(
        "step 1 action: work\nSUBTASK A--0\nanswer one\n\nSUBTASK B--0\nanswer two\n"
    )
    selected_run, selected_shots, answer = C.judgeable_run(tmp_path / "workspace")
    assert selected_run == run
    assert selected_shots == [str(shots / "final_execution_1_a_0.png")]
    assert answer.startswith("SUBTASK A--0")
    assert "SUBTASK B--0" in answer


def test_execution_failure_counts_each_subtask_as_failed(tmp_path):
    tasks = {
        "A--0": {"ques": "first", "web": "https://a.test/", "web_name": "A"},
        "B--0": {"ques": "second", "web": "https://b.test/", "web_name": "B"},
    }
    bundle = {"id": "bundle", "scope": "cross_site", "task_ids": ["A--0", "B--0"]}
    records = C.execution_failure_records(bundle, tasks, tmp_path, "scratch", "no final")
    assert [row["predicted_label"] for row in records] == [0, 0]
    assert all(row["judge_mode"] == "WebVoyager_composite_execution_failure" for row in records)
