import importlib.util
import json
from pathlib import Path


_PATH = Path(__file__).parents[2] / "evals" / "webarena" / "aggregate_cross_task_results.py"
_SPEC = importlib.util.spec_from_file_location("aggregate_cross_task_results", _PATH)
A = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(A)

_RUNNER_PATH = Path(__file__).parents[2] / "evals" / "webarena" / "run_cross_task_plan.py"
_RUNNER_SPEC = importlib.util.spec_from_file_location("run_cross_task_plan", _RUNNER_PATH)
P = importlib.util.module_from_spec(_RUNNER_SPEC)
_RUNNER_SPEC.loader.exec_module(P)


def test_plan_has_18_train_jobs_and_24_paired_test_jobs():
    manifest = Path(__file__).parents[2] / "evals" / "webarena" / "splits_18_12" / "manifest.json"
    train = P.planned_jobs(manifest, "train")
    test = P.planned_jobs(manifest, "test")
    assert len(train) == 18
    assert len(test) == 24
    assert {mode for *_, mode in train} == {"scratch"}
    assert {mode for *_, mode in test} == {"scratch", "routed"}


def test_aggregate_reports_success_delta_wins_losses_and_skips(tmp_path):
    splits = tmp_path / "splits"
    results = tmp_path / "results" / "shopping"
    splits.mkdir()
    results.mkdir(parents=True)
    manifest = {
        "protocol": "cross-template train/test only",
        "test": {"total_tasks": 2},
        "sites": {"shopping": "shopping.json"},
    }
    (splits / "manifest.json").write_text(json.dumps(manifest))
    (splits / "shopping.json").write_text(json.dumps({
        "heldout": [{"intent_template_id": 1, "task_ids": [10, 11]}]
    }))
    records = {
        "task10_scratch": {"correct": False, "steps": 10},
        "task10_routed": {
            "correct": True, "steps": 8,
            "route_stage": "primitive", "route_decision": "adapt",
        },
        "task11_scratch": {"correct": True, "steps": 6},
        "task11_routed": {
            "correct": True, "steps": 6,
            "route_stage": "primitive", "route_decision": "skip",
        },
    }
    for name, payload in records.items():
        (results / f"{name}.json").write_text(json.dumps(payload))
    report = A.aggregate(splits / "manifest.json", tmp_path / "results")
    assert report["complete"] is True
    assert report["scratch_success_rate"] == 0.5
    assert report["routed_success_rate"] == 1.0
    assert report["success_rate_delta"] == 0.5
    assert report["wins"] == 1 and report["losses"] == 0
    assert report["route_decisions"] == {"adapt": 1, "skip": 1}
    assert report["by_route"]["primitive:adapt"]["wins"] == 1
    assert report["by_route"]["primitive:skip"]["ties_both_correct"] == 1
    assert report["scratch_mean_steps"] == 8
    assert report["routed_mean_steps"] == 7
