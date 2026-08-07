import importlib.util
import json
from pathlib import Path


_PATH = Path(__file__).parents[2] / "evals" / "webarena" / "prepare_admitted_sources.py"
_SPEC = importlib.util.spec_from_file_location("prepare_admitted_sources", _PATH)
P = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(P)


def test_collect_only_gold_admitted_selected_train_tasks(tmp_path):
    splits = tmp_path / "splits"
    results = tmp_path / "results" / "map"
    splits.mkdir()
    results.mkdir(parents=True)
    (splits / "manifest.json").write_text('{"sites":{"map":"map.json"}}')
    (splits / "map.json").write_text('{"source":{"task_ids":[1,2]}}')
    (results / "task1_scratch.json").write_text(json.dumps({
        "task_id": 1, "site": "map", "score": 1.0, "correct": True,
        "retrieved_primitives": [],
    }))
    (results / "task2_scratch.json").write_text(json.dumps({
        "task_id": 2, "site": "map", "score": 0.0, "correct": False,
        "retrieved_primitives": [],
    }))
    by_site, selected = P.collect(splits / "manifest.json", tmp_path / "results")
    assert selected == {"map": 2}
    assert by_site == {"map": [str(results / "task1_scratch.json")]}
