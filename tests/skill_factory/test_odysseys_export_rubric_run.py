import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "odysseys_export_rubric", ROOT / "evals/odysseys/export_rubric_run.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_export_accepts_arm_suffix_and_prefers_successful_run(tmp_path):
    workspace = tmp_path / "runs" / "t_scratch_stamp"
    workspace.mkdir(parents=True)
    (workspace / "task.json").write_text(json.dumps({"task_id": "t_scratch"}))
    for index, label in ((1, 1), (2, 0)):
        run = workspace / "final_runs" / f"run_{index:03d}"
        (run / "screenshots").mkdir(parents=True)
        (run / "final_script_log.txt").write_text(f"run {index}")
        (run / "self_reflect_result.json").write_text(json.dumps({"predicted_label": label}))
        (run / "screenshots" / f"final_execution_1_{index}.png").write_bytes(b"png")
    result = MODULE.export("t", tmp_path / "runs", tmp_path / "out")
    assert result["final_run"].endswith("run_001")
    assert (tmp_path / "out/t/result.txt").read_text() == "1.0\n"
