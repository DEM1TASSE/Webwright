import importlib.util
import signal
import subprocess
from pathlib import Path


_PATH = Path(__file__).parents[2] / "evals" / "webarena" / "cross_task_eval.py"
_SPEC = importlib.util.spec_from_file_location("cross_task_eval", _PATH)
E = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(E)


def test_prepare_routed_hint_uses_workflow_first_cross_template_policy(tmp_path):
    seen = {}

    def fake_route(task, library, **kwargs):
        seen.update(task=task, library=library, kwargs=kwargs)
        return {
            "action": "agent",
            "hint": "selected material",
            "route_stage": "primitive",
            "route_decision": "adapt",
        }

    task = {"intent": "summarize commits", "sites": ["gitlab"]}
    out = E.prepare_routed_hint(task, tmp_path, route_fn=fake_route)
    assert out["hint"] == "selected material"
    assert seen["kwargs"]["primitive_site"] == "gitlab"
    assert seen["kwargs"]["cross_template_workflow_first"] is True
    assert "agent_fn" not in seen["kwargs"]


def test_configure_router_model_uses_explicit_yaml_backend(tmp_path, monkeypatch):
    config = tmp_path / "model.yaml"
    config.write_text(
        "model:\n  model_class: openai\n  model_name: test-model\n"
        "  openai_endpoint: https://gateway.example/responses\n"
    )
    seen = []
    monkeypatch.setattr(
        "webwright.skill_factory.llm.configure_llm", lambda model: seen.append(model)
    )
    E.configure_router_model(config)
    assert seen == [{
        "model_class": "openai",
        "model_name": "test-model",
        "openai_endpoint": "https://gateway.example/responses",
    }]


def test_null_not_found_response_is_a_complete_artifact(tmp_path):
    run = tmp_path / "task7_scratch_001"
    run.mkdir()
    (run / "agent_response.json").write_text(
        '{"task_type":"RETRIEVE","status":"NOT_FOUND_ERROR",'
        '"retrieved_data":null,"error_details":null}'
    )
    assert E.has_complete_agent_response(tmp_path, "task7_scratch") is True
    assert E.collect_run(tmp_path, "task7_scratch")[1] is None


def test_missing_response_is_not_complete(tmp_path):
    run = tmp_path / "task8_scratch_001"
    run.mkdir()
    (run / "task.json").write_text("{}")
    assert E.has_complete_agent_response(tmp_path, "task8_scratch") is False


def test_terminate_process_group_escalates_after_grace_period(monkeypatch):
    calls = []

    class Proc:
        pid = 42

        def wait(self, timeout=None):
            calls.append(("wait", timeout))
            if timeout is not None:
                raise subprocess.TimeoutExpired("agent", timeout)

    monkeypatch.setattr(
        E.os, "killpg", lambda pid, sig: calls.append(("killpg", pid, sig))
    )
    E.terminate_process_group(Proc(), grace_seconds=3)
    assert calls == [
        ("killpg", 42, signal.SIGTERM),
        ("wait", 3),
        ("killpg", 42, signal.SIGKILL),
        ("wait", None),
    ]


def test_process_start_failure_is_infrastructure_not_benchmark_failure():
    assert E.classify_result(False, None, False, 1) == (
        None, "agent_process_infrastructure_error"
    )
    assert E.classify_result(False, None, True, -15) == (
        False, "agent_timeout_or_incomplete"
    )
    assert E.classify_result(True, 1.0, False, 0) == (True, "scored_correct")


def test_summarize_reports_routed_pairs_decisions_and_site_breakdown(tmp_path):
    split = {
        "site": "shopping",
        "heldout": [{"intent_template_id": 10, "task_ids": [1, 2]}],
        "gate": {
            "go_if_win_minus_loss_at_least": 1,
            "minimum_templates_with_wins": 1,
        },
    }
    records = {
        "task1_scratch": {"mode": "scratch", "correct": False},
        "task1_routed": {
            "mode": "routed", "correct": True, "intent_template_id": 10,
            "site": "shopping", "route_decision": "adapt",
            "code_incorporated_primitives": [], "declared_used_primitives": [],
        },
        "task2_scratch": {"mode": "scratch", "correct": True},
        "task2_routed": {
            "mode": "routed", "correct": True, "intent_template_id": 10,
            "site": "shopping", "route_decision": "skip",
            "code_incorporated_primitives": [], "declared_used_primitives": [],
        },
    }
    for stem, value in records.items():
        (tmp_path / f"{stem}.json").write_text(__import__("json").dumps(value))
    summary = E.summarize(split, tmp_path, tmp_path / "library")
    assert summary["comparison_mode"] == "routed"
    assert summary["scratch_correct"] == 1 and summary["routed_correct"] == 2
    assert summary["wins"] == 1 and summary["losses"] == 0
    assert summary["route_decisions"] == {"adapt": 1, "skip": 1}
    assert summary["by_site"]["shopping"]["routed_correct"] == 2
