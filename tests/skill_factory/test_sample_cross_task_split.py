import importlib.util
from pathlib import Path


_PATH = Path(__file__).parents[2] / "evals" / "webarena" / "sample_cross_task_split.py"
_SPEC = importlib.util.spec_from_file_location("sample_cross_task_split", _PATH)
S = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(S)


def task(task_id, template_id, site="map", task_type="retrieve"):
    return {
        "task_id": task_id,
        "intent_template_id": template_id,
        "sites": [site],
        "eval": [{
            "evaluator": "AgentResponseEvaluator",
            "expected": {"task_type": task_type},
        }],
    }


def test_sample_is_template_disjoint_and_input_order_independent():
    dataset = [task(t * 10 + i, t) for t in range(8) for i in range(2)]
    first = S.sample_site(dataset, "map", 7, 3, 2)
    second = S.sample_site(list(reversed(dataset)), "map", 7, 3, 2)
    assert first == second
    train = set(first["source"]["intent_template_ids"])
    test = {row["intent_template_id"] for row in first["heldout"]}
    assert not train & test
    assert len(first["source"]["task_ids"]) == 3
    assert all(len(row["task_ids"]) == 1 for row in first["heldout"])


def test_eligibility_rejects_mutate_and_extra_evaluators():
    good = task(1, 1)
    mutate = task(2, 2, task_type="mutate")
    extra = task(3, 3)
    extra["eval"].append({"evaluator": "NetworkEventEvaluator"})
    assert S.eligible_tasks([good, mutate, extra], "map") == [good]
