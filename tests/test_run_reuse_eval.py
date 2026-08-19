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
    assert MODULE.build_jobs(split, "t1") == [("map", "retrieve", 1, 2),
                                                 ("map", "retrieve", 1, 3)]
    assert MODULE.build_jobs(split, "t2") == [("map", "retrieve", 9, 8)]
    assert MODULE.build_jobs(split, "t2", ["gitlab"]) == []
    assert MODULE.build_jobs(split, "t2", ["map"]) == [("map", "retrieve", 9, 8)]


def test_select_task_subset_stays_inside_frozen_partition():
    jobs = [("map", "retrieve", 9, 8), ("gitlab", "retrieve", 10, 12)]
    assert MODULE.select_task_subset(jobs, [12], []) == [jobs[1]]
    assert MODULE.select_task_subset(jobs, None, [8]) == [jobs[1]]
    try:
        MODULE.select_task_subset(jobs, [999], [])
    except ValueError as error:
        assert "outside selected frozen partition" in str(error)
    else:
        raise AssertionError("unknown task must not be silently ignored")


def test_compat_splits_are_site_local(tmp_path):
    jobs = [
        ("gitlab", "retrieve", 10, 1),
        ("map", "navigate", 20, 2),
        ("gitlab", "retrieve", 11, 3),
    ]
    paths = MODULE.write_site_compat_splits(tmp_path, "t2", "primitive", jobs)
    assert set(paths) == {"gitlab", "map"}
    assert json.loads(paths["gitlab"].read_text())["heldout"] == [
        {"intent_template_id": 10, "task_ids": [1]},
        {"intent_template_id": 11, "task_ids": [3]},
    ]
    assert json.loads(paths["map"].read_text())["heldout"] == [
        {"intent_template_id": 20, "task_ids": [2]},
    ]


def test_task_compat_splits_preserve_task_type(tmp_path):
    jobs = [
        ("map", "retrieve", 10, 1),
        ("map", "navigate", 20, 2),
    ]
    paths = MODULE.write_task_compat_splits(tmp_path, "t2", "scratch", jobs)
    assert json.loads(paths[("map", 1)].read_text()) == {
        "task_type": "retrieve",
        "heldout": [{"intent_template_id": 10, "task_ids": [1]}],
    }
    assert json.loads(paths[("map", 2)].read_text()) == {
        "task_type": "navigate",
        "heldout": [{"intent_template_id": 20, "task_ids": [2]}],
    }


def test_workflow_map_only_uses_successful_builds(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(json.dumps([
        {"site": "map", "template_id": 1, "status": "built", "skill_ids": ["wf1"]},
        {"site": "map", "template_id": 2, "status": "failed", "skill_ids": ["wf2"]},
    ]))
    assert MODULE.workflow_map(path) == {("map", 1): "wf1"}


def test_select_deployment_distributes_by_task_id_without_mutating_input():
    config = {"environments": {
        "__SHOPPING__": {"urls": ["http://a", "http://b", "http://c"]},
    }}
    selected, url = MODULE.select_deployment(config, "shopping", 5)
    assert url == "http://c"
    assert selected["environments"]["__SHOPPING__"]["urls"] == ["http://c"]
    assert selected["assignment"]["replica_index"] == 2
    assert config["environments"]["__SHOPPING__"]["urls"] == [
        "http://a", "http://b", "http://c",
    ]


def test_write_job_deployment_config_records_assignment(tmp_path):
    config = {"environments": {"__MAP__": {"urls": ["http://m0", "http://m1"]}}}
    path, url = MODULE.write_job_deployment_config(
        tmp_path, "t2", "scratch", config, "map", 3,
    )
    assert url == "http://m1"
    saved = json.loads(path.read_text())
    assert saved["environments"]["__MAP__"]["urls"] == ["http://m1"]
    assert saved["assignment"]["task_id"] == 3
