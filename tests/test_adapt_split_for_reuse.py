import importlib.util
import json
from pathlib import Path


SCRIPT = (Path(__file__).parents[1] / "skills" / "official-webarena" / "scripts"
          / "adapt_split_for_reuse.py")
SPEC = importlib.util.spec_from_file_location("adapt_split_for_reuse", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_adapt_nested_results_and_official_id_split(tmp_path):
    dataset = [
        {"task_id": 1, "sites": ["shopping"], "intent_template_id": 10, "intent": "a"},
        {"task_id": 2, "sites": ["wikipedia"], "intent_template_id": 20, "intent": "b"},
    ]
    split = {"tier": "cross_template", "train": [1], "test": [2],
             "template_meta": {"10": {"type": "retrieve"}, "20": {"type": "navigate"}}}
    runs = tmp_path / "runs"
    (runs / "task1").mkdir(parents=True)
    (runs / "task1" / "final_script.py").write_text("pass\n", encoding="utf-8")
    roots = [tmp_path / "nonmutate", tmp_path / "mutate"]
    dump(roots[0] / "shopping" / "task1.json",
         {"run": {"run_dir": str(runs / "task1")},
          "evaluation": {"score": 1.0, "status": "scored_correct"}})
    dump(roots[0] / "wikipedia" / "task2.json",
         {"run": {"run_dir": str(runs / "missing")},
          "evaluation": {"score": 0.0, "status": "scored_incorrect"}})

    manifest = MODULE.adapt(split, dataset, roots, tmp_path / "out",
                            split_path=tmp_path / "split.json",
                            dataset_path=tmp_path / "dataset.json")

    assert manifest["counts"] == {"train": 1, "test": 1,
                                  "train_gold_admitted": 1,
                                  "test_baseline_correct": 0}
    reuse = MODULE.load(tmp_path / "out" / "reuse_split.json")
    assert reuse["train"]["shopping"][0]["build_task_ids"] == [1]
    assert reuse["test"]["wikipedia"][0]["t2_task_ids"] == [2]
    normalized = MODULE.load(
        tmp_path / "out" / "normalized_results" / "shopping" / "task1_scratch.json")
    assert normalized["correct"] is True
    assert normalized["retrieved_primitives"] == []
