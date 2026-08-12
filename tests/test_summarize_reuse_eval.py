import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals/webarena/summarize_reuse_eval.py"
SPEC = importlib.util.spec_from_file_location("summarize_reuse_eval", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_paired_counts_wins_losses_and_step_delta():
    jobs = [("map", 1, 10), ("map", 1, 11), ("gitlab", 2, 12)]
    base = {10: {"correct": False, "steps": 9}, 11: {"correct": True, "steps": 8},
            12: {"correct": True, "steps": 10}}
    treatment = {10: {"correct": True, "steps": 7}, 11: {"correct": False, "steps": 6},
                 12: {"correct": True, "steps": 8}}
    out = MODULE.paired(base, treatment, jobs)
    assert (out["wins"], out["losses"], out["net_wins"]) == (1, 1, 0)
    assert out["mean_step_delta_on_both_correct"] == -2


def test_arm_metrics_reports_exposure():
    rows = {1: {"correct": True, "steps": 4, "retrieved_primitives": [{"id": "p"}],
                "primitive_execution_trace": [{"event": "entered"}]}}
    out = MODULE.arm_metrics(rows, [1, 2])
    assert out["expected"] == 2 and out["observed"] == 1
    assert out["primitive_exposed"] == 1 and out["primitive_executed"] == 1
