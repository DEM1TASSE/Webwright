import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals/webarena/run_reuse_split.py"
SPEC = importlib.util.spec_from_file_location("run_reuse_split", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_build_jobs_reads_only_train_build_tasks():
    split = {
        "train": {
            "gitlab": [{"build_task_ids": [1, 2]}],
            "map": [{"build_task_ids": [3]}],
        },
        "test": {"gitlab": [{"t2_task_ids": [4]}], "map": []},
    }
    assert MODULE.build_jobs(split) == [("gitlab", 1), ("gitlab", 2), ("map", 3)]


def test_site_lanes_are_sequential_and_site_isolated():
    lanes = MODULE.site_lanes([
        ("gitlab", 1), ("map", 2), ("gitlab", 3), ("map", 4),
    ])
    assert lanes == [[("gitlab", 1), ("gitlab", 3)], [("map", 2), ("map", 4)]]


def test_site_lanes_bound_intrasite_concurrency():
    lanes = MODULE.site_lanes([
        ("gitlab", 1), ("gitlab", 2), ("gitlab", 3), ("gitlab", 4),
    ], per_site_workers=2)
    assert lanes == [[("gitlab", 1), ("gitlab", 3)],
                     [("gitlab", 2), ("gitlab", 4)]]


def test_frozen_split_has_no_task_or_template_leakage():
    split = json.loads((SCRIPT.parent / "reuse_split_v1.json").read_text())
    build, t1, t2 = set(), set(), set()
    for site, rows in split["train"].items():
        train_templates = {row["intent_template_id"] for row in rows}
        test_templates = {row["intent_template_id"] for row in split["test"][site]}
        assert train_templates.isdisjoint(test_templates)
        for row in rows:
            build.update(row["build_task_ids"])
            t1.update(row["t1_heldout_task_ids"])
        for row in split["test"][site]:
            t2.update(row["t2_task_ids"])
    assert build.isdisjoint(t1)
    assert build.isdisjoint(t2)
    assert t1.isdisjoint(t2)
