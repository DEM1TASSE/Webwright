import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[2]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WV = _load("wv_for_odysseys_test", "evals/webvoyager/pipeline.py")
EXPORT = _load("odysseys_export_test", "evals/odysseys/export_rubric_run.py")


def test_odysseys_task_fields_are_supported(tmp_path):
    task = {"task_id": "abc", "confirmed_task": "multi-site task",
            "website": "https://www.google.com", "level": "easy"}
    assert WV.task_text(task) == "multi-site task"
    command = WV.solve_command(task, "abc", "scratch", tmp_path, "", ["model.yaml"])
    assert "multi-site task" in command
    assert "https://www.google.com" in command


def test_export_official_rubric_layout(tmp_path):
    runs = tmp_path / "runs"
    workspace = runs / "abc_timestamp"
    final = workspace / "final_runs" / "run_001"
    shots = final / "screenshots"
    shots.mkdir(parents=True)
    (workspace / "task.json").write_text(json.dumps({"task_id": "abc"}))
    (final / "final_script_log.txt").write_text("opened pages\nfinal answer")
    (final / "self_reflect_result.json").write_text("{}")
    (shots / "final_execution_1_page.png").write_bytes(b"png")
    result = EXPORT.export("abc", runs, tmp_path / "rubric")
    output = Path(result["output"])
    assert (output / "result.txt").read_text() == "1.0\n"
    row = json.loads((output / "steps.jsonl").read_text().splitlines()[0])
    assert row["action"] == "opened pages\nfinal answer"
    assert row["screenshot"].endswith("final_execution_1_page.png")
