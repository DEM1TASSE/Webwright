import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals/webarena/prune_reuse_split_to_retrieve.py"
SPEC = importlib.util.spec_from_file_location("prune_reuse", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def task(task_id, intent, task_type="retrieve"):
    return {"task_id": task_id, "intent": intent, "sites": ["reddit"],
            "intent_template_id": task_id,
            "eval": [{"evaluator": "AgentResponseEvaluator",
                      "expected": {"task_type": task_type}}]}


def test_prune_removes_mutation_semantics_and_expected_type():
    split = {"design": {}, "train": {"reddit": []}, "test": {"reddit": [
        {"intent_template_id": 1, "t2_task_ids": [1], "unseen_in_earlier_splits": True},
        {"intent_template_id": 2, "t2_task_ids": [2], "unseen_in_earlier_splits": True},
        {"intent_template_id": 3, "t2_task_ids": [3], "unseen_in_earlier_splits": True},
    ]}}
    corrected, removed_train, removed_t2 = MODULE.prune(split, [
        task(1, "Get all posts"), task(2, "Like all posts"),
        task(3, "Submit a post", task_type="mutate"),
    ])
    assert removed_train == []
    assert removed_t2 == [2, 3]
    assert [row["intent_template_id"] for row in corrected["test"]["reddit"]] == [1]


def test_open_issue_is_mutation_even_when_expected_as_retrieve_error():
    split = {"design": {}, "train": {"reddit": []}, "test": {"reddit": [
        {"intent_template_id": 4, "t2_task_ids": [4], "unseen_in_earlier_splits": True},
    ]}}
    corrected, _, removed_t2 = MODULE.prune(
        split, [task(4, "Open an issue asking for WebAgent support")])
    assert corrected["test"]["reddit"] == []
    assert removed_t2 == [4]


def test_prune_removes_ineligible_train_source():
    split = {"design": {}, "train": {"reddit": [{
        "intent_template_id": 2, "build_task_ids": [2], "t1_heldout_task_ids": []
    }]}, "test": {"reddit": []}}
    corrected, removed_train, removed_t2 = MODULE.prune(
        split, [task(2, "Delete all posts")])
    assert corrected["train"]["reddit"] == []
    assert removed_train == [2]
    assert removed_t2 == []
