import json

from webwright.skill_factory.webvoyager_eval import (
    evaluate_task, load_final_response, load_task_map, verdict_label,
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
    assert verdict_label("Evidence supports completion. **VERDICT: SUCCESS**") == 1
    assert verdict_label("SUCCESS maybe") is None


def test_load_multiline_response_and_response_file(tmp_path):
    run = tmp_path / "run_1"
    run.mkdir()
    (run / "final_script_log.txt").write_text(
        "step 8 final_response:\nline one\nline two\nstep 9 action: cleanup\n"
    )
    assert load_final_response(run) == "line one\nline two"
    (run / "final_response.txt").write_text("canonical\nanswer\n")
    assert load_final_response(run) == "canonical\nanswer"


def test_evaluate_task_uses_three_vote_majority(tmp_path):
    workspace = tmp_path / "GitHub--0_run"
    run = workspace / "final_runs" / "run_1"
    shots = run / "screenshots"
    shots.mkdir(parents=True)
    (run / "final_script_log.txt").write_text("FINAL_RESPONSE: answer\n")
    (shots / "one.png").write_bytes(b"png")

    class Engine:
        model = "gpt-4o"
        responses = iter(("VERDICT: SUCCESS", "VERDICT: NOT SUCCESS", "VERDICT: SUCCESS"))
        def generate(self, *_args, **_kwargs):
            return [next(self.responses)]

    record = evaluate_task(
        "GitHub--0", workspace,
        {"task": "do it", "website": "https://github.com", "web_name": "GitHub"},
        Engine(), repetitions=3,
    )
    assert record["judge_labels"] == [1, 0, 1]
    assert record["predicted_label"] == 1
