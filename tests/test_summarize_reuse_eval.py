import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals/webarena/summarize_reuse_eval.py"
SPEC = importlib.util.spec_from_file_location("summarize_reuse_eval", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_paired_counts_wins_losses_and_step_delta():
    terminal = {"run_status": "scored_correct"}
    base = {task_id: {**terminal, "task_id": task_id, "site": "map",
                      "intent_template_id": 1, "correct": correct, "steps": steps}
            for task_id, correct, steps in ((10, False, 9), (11, True, 8), (12, True, 10))}
    treatment = {task_id: {**terminal, "task_id": task_id, "site": "map",
                           "intent_template_id": 1, "route_decision": "adapt",
                           "correct": correct, "steps": steps}
                 for task_id, correct, steps in ((10, True, 7), (11, False, 6),
                                                  (12, True, 8))}
    out = MODULE.paired(base, treatment)
    assert (out["win"], out["loss"], out["net_wins"]) == (1, 1, 0)
    assert out["mean_step_delta_when_both_correct"] == -2


def test_arm_summary_reports_exposure_and_ignores_infrastructure_errors():
    rows = [{"site": "map", "intent_template_id": 1,
             "run_status": "scored_correct", "correct": True,
             "steps": 4, "retrieved_primitives": [{"id": "p"}],
             "code_incorporated_primitives": ["p"], "declared_used_primitives": ["p"],
             "primitive_execution_trace": [{"event": "entered"}]},
            {"site": "map", "run_status": "agent_process_infrastructure_error",
             "correct": None, "steps": 20}]
    out = MODULE.arm_summary(rows)
    assert out["n"] == 2 and out["terminal"] == 1
    assert out["primitive_exposed"] == 1 and out["primitive_code_incorporated"] == 1
    assert out["primitive_usage_declared"] == 1 and out["primitive_execution_traced"] == 1


def test_paired_excludes_nonterminal_infrastructure_error():
    base = {1: {"task_id": 1, "site": "map", "intent_template_id": 1,
                "run_status": "scored_incorrect",
                "correct": False, "steps": 4},
            2: {"task_id": 2, "site": "map",
                "run_status": "agent_process_infrastructure_error", "correct": None,
                "steps": 2}}
    treatment = {1: {"task_id": 1, "site": "map", "intent_template_id": 1,
                     "run_status": "scored_correct",
                     "correct": True, "steps": 3},
                 2: {"task_id": 2, "site": "map", "run_status": "scored_correct",
                     "correct": True, "steps": 3}}
    out = MODULE.paired(base, treatment)
    assert out["pairs"] == 1 and out["win"] == 1


def test_isolation_checks_scratch_and_primitive_selection():
    assert not MODULE.isolation_errors(
        {"task_id": 1, "route_stage": None, "route_decision": None,
         "retrieved_primitives": [], "routed_workflow_id": None}, "t2", "scratch")
    errors = MODULE.isolation_errors(
        {"task_id": 1, "route_stage": "primitive", "route_decision": "adapt",
         "retrieved_primitives": [], "routed_workflow_id": None}, "t2", "primitive")
    assert errors == ["t2/primitive/task1: selected primitive code is missing"]
