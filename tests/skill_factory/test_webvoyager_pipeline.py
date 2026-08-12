import importlib.util
import json
from pathlib import Path


PATH = Path(__file__).parents[2] / "evals" / "webvoyager" / "pipeline.py"
SPEC = importlib.util.spec_from_file_location("webvoyager_pipeline", PATH)
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


def test_official_task_and_commands(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text(json.dumps({"web_name": "GitHub", "id": "GitHub--0",
                                "ques": "find repo", "web": "https://github.com/"}) + "\n")
    task = P.tasks_by_id(path)["GitHub--0"]
    scratch = P.solve_command(task, "GitHub--0", "scratch", tmp_path, "lib", ["model.yaml"])
    routed = P.solve_command(task, "GitHub--0", "routed", tmp_path, "lib", ["model.yaml"])
    assert "webwright.run.cli" in scratch
    assert "webwright.skill_factory" in routed
    assert "--primitive-site" in routed and "github_com" in routed
    assert scratch[-4:] == ["-c", "base.yaml", "-c", "model.yaml"]


def test_materialize_records_actual_treatment(tmp_path):
    runs = tmp_path / "runs"; workspace = runs / "GitHub--0_timestamp"
    workspace.mkdir(parents=True)
    (workspace / "task.json").write_text(json.dumps({"task_id": "GitHub--0"}))
    (workspace / "primitive_usage.json").write_text(json.dumps({
        "used": [{"primitive_id": "github/search", "content_hash": "sha256:x"}]
    }))
    (runs / "GitHub--0.primitive_retrieval.json").write_text(json.dumps({
        "primitive_ids": ["github/search"]
    }))
    judge = tmp_path / "judge.jsonl"
    judge.write_text(json.dumps({"task_id": "GitHub--0", "predicted_label": 1,
                                 "judge_mode": "WebVoyager_original_protocol"}) + "\n")
    task = {"web_name": "GitHub", "id": "GitHub--0", "ques": "find repo",
            "web": "https://github.com/"}
    record = P.materialize(task, "GitHub--0", "routed", runs, judge)
    assert record["correct"] is True
    assert record["primitive_selected"] is True
    assert record["primitive_used"] is True
    assert record["primitive_ids"] == ["github/search"]


def test_compare_does_not_conflate_routed_with_treatment():
    result = P.compare({"task_id": "t", "correct": False},
                       {"task_id": "t", "correct": True,
                        "primitive_selected": False, "primitive_used": False})
    assert result["delta"] == 1
    assert result["primitive_used"] is False

