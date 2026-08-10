import json
from pathlib import Path

from webwright.skill_factory.om2w_eval import (
    discover_task_dirs, latest_run, load_actions, load_screenshots, load_task_map,
)


def test_artifact_bridge(tmp_path):
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps([
        {"task_id": "t1", "confirmed_task": "confirmed"},
        {"task_id": "t2", "task": "fallback"},
    ]))
    assert load_task_map(tasks) == {"t1": "confirmed", "t2": "fallback"}

    task = tmp_path / "t1"
    old = task / "final_runs" / "run_2"
    new = task / "final_runs" / "run_10"
    (old / "screenshots").mkdir(parents=True)
    (new / "screenshots").mkdir(parents=True)
    assert latest_run(task) == new

    (new / "final_script_log.txt").write_text(
        "step 1 action: navigate\\nstep 2 action: filter\nFINAL ANSWER: do not judge this\n"
    )
    assert load_actions(new / "final_script_log.txt") == [
        "step 1 action: navigate", "step 2 action: filter"
    ]

    for name in ("final_execution_10_end.png", "final_execution_2_filter.png", "cp1_open.png"):
        (new / "screenshots" / name).write_bytes(b"png")
    names = [Path(p).name for p in load_screenshots(new / "screenshots")]
    assert names == ["final_execution_2_filter.png", "final_execution_10_end.png", "cp1_open.png"]


def test_official_field_and_timestamped_workspace(tmp_path):
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps([{"task_id": "abc", "task_description": "official"}]))
    assert load_task_map(tasks) == {"abc": "official"}
    workspace = tmp_path / "abc_20260101_000001"
    workspace.mkdir()
    (workspace / "task.json").write_text(json.dumps({"task_id": "abc"}))
    assert discover_task_dirs(tmp_path, {"abc"}) == {"abc": workspace}
