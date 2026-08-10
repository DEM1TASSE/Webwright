import importlib.util
import json
from pathlib import Path


PATH = Path(__file__).parents[2] / "evals" / "om2w" / "smoke_pipeline.py"
SPEC = importlib.util.spec_from_file_location("om2w_smoke_pipeline", PATH)
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


def test_site_slug_and_commands(tmp_path):
    task = {"website": "https://www.accuweather.com/", "confirmed_task": "monthly"}
    assert P.site_slug(task["website"]) == "accuweather_com"
    scratch = P.solve_command(task, "t1", "scratch", tmp_path, "lib", ["model.yaml"])
    routed = P.solve_command(task, "t1", "routed", tmp_path, "lib", ["model.yaml"])
    assert "webwright.run.cli" in scratch
    assert "webwright.skill_factory" in routed
    assert scratch[-4:] == ["-c", "base.yaml", "-c", "model.yaml"]
    assert "--primitive-site" in routed and "accuweather_com" in routed


def test_materialize_missing_judge_fails_closed(tmp_path):
    runs = tmp_path / "runs"
    workspace = runs / "t1_20260101_000000"
    workspace.mkdir(parents=True)
    (workspace / "task.json").write_text(json.dumps({"task_id": "t1"}))
    task = {"website": "https://www.example.com/", "confirmed_task": "do it"}
    record = P.materialize(task, "t1", "scratch", runs, tmp_path / "missing.jsonl")
    assert record["correct"] is None
    assert record["run_status"] == "evaluator_infrastructure_error"


def test_compare_is_paired_and_incomplete_safe():
    win = P.compare({"task_id": "t", "correct": False},
                    {"task_id": "t", "correct": True})
    assert win["win"] is True and win["delta"] == 1
    incomplete = P.compare({"task_id": "t", "correct": None},
                           {"task_id": "t", "correct": True})
    assert incomplete["complete"] is False and incomplete["delta"] is None
