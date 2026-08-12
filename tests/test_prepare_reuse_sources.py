import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals/webarena/prepare_reuse_sources.py"
SPEC = importlib.util.spec_from_file_location("prepare_reuse_sources", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_prepare_gold_gates_and_groups(tmp_path):
    split = tmp_path / "split.json"
    results = tmp_path / "results"
    run = tmp_path / "run"
    run.mkdir()
    (run / "final_script.py").write_text("pass\n")
    write(split, {"train": {"map": [{"intent_template_id": 7,
                                       "build_task_ids": [1, 2]}]}})
    base = {"site": "map", "intent_template_id": 7, "score": 1.0,
            "correct": True, "retrieved_primitives": [], "run_dir": str(run)}
    write(results / "map/task1_scratch.json", {**base, "task_id": 1})
    write(results / "map/task2_scratch.json", {**base, "task_id": 2,
                                                 "correct": False, "score": 0.0})
    out = MODULE.prepare(split, results)
    assert out["attempted"] == 2
    assert out["admitted"] == 1
    assert out["by_site"]["map"] == [str((results / "map/task1_scratch.json").resolve())]
    assert out["by_template"]["map"]["7"] == out["by_site"]["map"]


def test_prepare_rejects_library_exposure(tmp_path):
    split = tmp_path / "split.json"
    results = tmp_path / "results"
    write(split, {"train": {"map": [{"intent_template_id": 7, "build_task_ids": [1]}]}})
    write(results / "map/task1_scratch.json", {
        "task_id": 1, "site": "map", "intent_template_id": 7,
        "score": 1.0, "correct": True, "retrieved_primitives": [{"id": "x"}],
    })
    try:
        MODULE.prepare(split, results)
    except ValueError as exc:
        assert "consumed primitive" in str(exc)
    else:
        raise AssertionError("expected contamination rejection")
