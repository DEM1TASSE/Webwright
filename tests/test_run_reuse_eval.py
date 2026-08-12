import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals/webarena/run_reuse_eval.py"
SPEC = importlib.util.spec_from_file_location("run_reuse_eval", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_build_jobs_keeps_t1_and_t2_disjoint():
    split = {
        "train": {"map": [{"intent_template_id": 1, "build_task_ids": [1],
                            "t1_heldout_task_ids": [2, 3]}]},
        "test": {"map": [{"intent_template_id": 9, "t2_task_ids": [8]}]},
    }
    assert MODULE.build_jobs(split, "t1") == [("map", 1, 2), ("map", 1, 3)]
    assert MODULE.build_jobs(split, "t2") == [("map", 9, 8)]


def test_workflow_map_only_uses_successful_builds(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(json.dumps([
        {"site": "map", "template_id": 1, "status": "built", "skill_ids": ["wf1"]},
        {"site": "map", "template_id": 2, "status": "failed", "skill_ids": ["wf2"]},
    ]))
    assert MODULE.workflow_map(path) == {("map", 1): "wf1"}
