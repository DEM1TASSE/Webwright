import importlib.util
import json
from pathlib import Path

import pytest


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
        (run / "screenshots" / f"final_execution_1_{index}.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"test"
        )
    result = MODULE.export("t", tmp_path / "runs", tmp_path / "out")
    assert result["final_run"].endswith("run_001")
    assert (tmp_path / "out/t/result.txt").read_text() == "1.0\n"


def test_export_rejects_run_without_self_reflection_by_default(tmp_path):
    workspace = tmp_path / "runs" / "t_primitive_stamp"
    run = workspace / "final_runs" / "run_001"
    run.mkdir(parents=True)
    (workspace / "task.json").write_text(json.dumps({"task_id": "t_primitive"}))
    (run / "final_script_log.txt").write_text("partial")

    with pytest.raises(ValueError, match="no self-reflected final run"):
        MODULE.export("t", tmp_path / "runs", tmp_path / "out")

    result = MODULE.export(
        "t", tmp_path / "runs", tmp_path / "debug", allow_incomplete=True,
    )
    assert result["final_run"].endswith("run_001")


def test_export_accepts_reflected_failure_for_per_rubric_scoring(tmp_path):
    workspace = tmp_path / "runs" / "t_scratch_stamp"
    run = workspace / "final_runs" / "run_001"
    run.mkdir(parents=True)
    (workspace / "task.json").write_text(json.dumps({"task_id": "t_scratch"}))
    (run / "final_script_log.txt").write_text("partial rubric evidence")
    (run / "self_reflect_result.json").write_text(
        json.dumps({"predicted_label": 0})
    )
    result = MODULE.export("t", tmp_path / "runs", tmp_path / "out")
    assert result["final_run"].endswith("run_001")
    with pytest.raises(ValueError, match="no self-reflection-passing final run"):
        MODULE.export(
            "t", tmp_path / "runs", tmp_path / "strict",
            require_self_reflection_pass=True,
        )


def test_export_filters_paired_workspaces_by_mode(tmp_path):
    for mode, contents in (("scratch", "scratch evidence"),
                           ("primitive", "primitive evidence")):
        workspace = tmp_path / "runs" / f"t_{mode}_stamp"
        run = workspace / "final_runs" / "run_001"
        run.mkdir(parents=True)
        (workspace / "task.json").write_text(json.dumps({"task_id": f"t_{mode}"}))
        (run / "final_script_log.txt").write_text(contents)
        (run / "self_reflect_result.json").write_text(
            json.dumps({"predicted_label": 1})
        )

    scratch = MODULE.export(
        "t", tmp_path / "runs", tmp_path / "scratch-out", mode="scratch",
    )
    primitive = MODULE.export(
        "t", tmp_path / "runs", tmp_path / "primitive-out", mode="primitive",
    )
    assert "_scratch_" in scratch["workspace"]
    assert "_primitive_" in primitive["workspace"]
    assert (tmp_path / "scratch-out/t/final_script_log.txt").read_text() == "scratch evidence"
    assert (tmp_path / "primitive-out/t/final_script_log.txt").read_text() == "primitive evidence"


def test_export_omits_text_file_with_png_extension(tmp_path):
    workspace = tmp_path / "runs" / "t_primitive_stamp"
    run = workspace / "final_runs" / "run_001"
    (run / "screenshots").mkdir(parents=True)
    (workspace / "task.json").write_text(json.dumps({"task_id": "t_primitive"}))
    (run / "final_script_log.txt").write_text("usable text evidence")
    (run / "self_reflect_result.json").write_text(json.dumps({"predicted_label": 1}))
    (run / "screenshots/final_execution_1_fake.png").write_text("not an image")

    result = MODULE.export(
        "t", tmp_path / "runs", tmp_path / "out", mode="primitive",
    )
    assert result["screenshots"] == 0
    assert result["invalid_screenshots_omitted"] == ["final_execution_1_fake.png"]
    row = json.loads((tmp_path / "out/t/steps.jsonl").read_text())
    assert "screenshot" not in row


def test_export_can_pin_an_exact_executed_final_run(tmp_path):
    workspace = tmp_path / "runs" / "t_primitive_stamp"
    (workspace / "task.json").parent.mkdir(parents=True)
    (workspace / "task.json").write_text(json.dumps({"task_id": "t_primitive"}))
    for name, contents in (("run_003", "old"), ("run_004", "fixed")):
        run = workspace / "final_runs" / name
        run.mkdir(parents=True)
        (run / "final_script_log.txt").write_text(contents)

    result = MODULE.export(
        "t", tmp_path / "runs", tmp_path / "out", mode="primitive",
        final_run="run_004",
    )
    assert result["final_run"].endswith("run_004")
    assert (tmp_path / "out/t/final_script_log.txt").read_text() == "fixed"

    with pytest.raises(ValueError, match="invalid final run name"):
        MODULE.export(
            "t", tmp_path / "runs", tmp_path / "bad", mode="primitive",
            final_run="../run_004",
        )
