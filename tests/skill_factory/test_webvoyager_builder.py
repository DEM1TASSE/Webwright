import importlib.util
import json
from pathlib import Path


PATH = Path(__file__).parents[2] / "evals" / "webvoyager" / "build_generated_primitives.py"
SPEC = importlib.util.spec_from_file_location("webvoyager_builder", PATH)
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)


def test_admitted_workflows_from_official_jsonl(tmp_path):
    dataset = tmp_path / "tasks.jsonl"
    rows = [
        {"web_name": "GitHub", "id": "GitHub--0", "ques": "search repo",
         "web": "https://github.com/"},
        {"web_name": "GitHub", "id": "GitHub--1", "ques": "inspect repo",
         "web": "https://github.com/"},
    ]
    dataset.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    judge = tmp_path / "judge.jsonl"
    judge.write_text("\n".join(json.dumps({"task_id": row["id"], "predicted_label": 1})
                                for row in rows) + "\n")
    runs = tmp_path / "runs"
    for row in rows:
        workspace = runs / (row["id"] + "_timestamp")
        run = workspace / "final_runs" / "run_1"
        run.mkdir(parents=True)
        (workspace / "task.json").write_text(json.dumps({"task_id": row["id"]}))
        (run / "final_script.py").write_text("async def solve(page): pass\n")
        (run / "final_script_log.txt").write_text("done\n")
    workflows = B.admitted_workflows(
        dataset, runs, judge, {"GitHub--0": "search", "GitHub--1": "inspect"}
    )
    assert [row["template_id"] for row in workflows] == ["search", "inspect"]
    assert {row["site"] for row in workflows} == {"github_com"}
