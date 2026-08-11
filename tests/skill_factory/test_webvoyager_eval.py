import json

from webwright.skill_factory.webvoyager_eval import (
    load_final_response, load_task_map, verdict_label,
)


def test_load_official_jsonl(tmp_path):
    path = tmp_path / "tasks.jsonl"
    path.write_text(json.dumps({
        "web_name": "GitHub", "id": "GitHub--0", "ques": "find repo",
        "web": "https://github.com/",
    }) + "\n")
    assert load_task_map(path)["GitHub--0"]["task"] == "find repo"


def test_final_response_and_verdict_are_strict(tmp_path):
    run = tmp_path / "task" / "final_runs" / "run_1"
    run.mkdir(parents=True)
    (run / "final_script_log.txt").write_text(
        "step 1 action: search\nFINAL_RESPONSE: first\nFinal answer: second\n"
    )
    assert load_final_response(run) == "second"
    assert verdict_label("reason\nVERDICT: SUCCESS") == 1
    assert verdict_label("reason\nVERDICT: NOT SUCCESS") == 0
    assert verdict_label("Evidence supports completion. VERDICT: SUCCESS") == 1
    assert verdict_label("SUCCESS maybe") is None
