"""Unit test: learn's LLM-free plumbing (schema inference, run collection, ledger skip)."""
import json, tempfile
from pathlib import Path
from webwright.skills.learn import infer_schema, collect_runs


def run():
    assert infer_schema([1, 2]) == {"type": "array", "items": {"type": "number"}}
    assert infer_schema(["a"]) == {"type": "array", "items": {"type": "string"}}
    assert infer_schema(7) == {"type": "number"}
    assert infer_schema({"k": 1}) == {"type": "object"}
    assert infer_schema("x") == {"type": "string"}

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        d1 = td / "run_a"; d1.mkdir()
        (d1 / "task.json").write_text(json.dumps(
            {"task": "## Skill library\nblah\n---\nCount commits by Jane Additionally, "
                     "write the final answer into $WORKSPACE_DIR/agent_response.json as {...}.",
             "task_id": "a", "start_url": "http://gitlab.example.com/x"}))
        (d1 / "agent_response.json").write_text(json.dumps({"retrieved_data": [3]}))
        d2 = td / "run_b"; d2.mkdir()   # unfinished: no agent_response
        (d2 / "task.json").write_text(json.dumps({"task": "t", "task_id": "b"}))

        runs = collect_runs(td, {"runs": {}})
        assert len(runs) == 1 and runs[0]["task_id"] == "a", runs
        assert runs[0]["task"] == "Count commits by Jane", "hint AND answer-spec must be stripped"
        assert runs[0]["answer"] == [3]

        # ledger makes it idempotent
        runs2 = collect_runs(td, {"runs": {str(d1.resolve()): {}}})
        assert runs2 == [], "already-learned run must be skipped"
    print("test_learn OK")


def run_regressions():
    """F3: grouping-LLM failure must exit with an actionable one-liner, not a traceback."""
    import webwright.skills.learn as L
    orig = L.llm_json
    L.llm_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("401 unauthorized"))
    try:
        try:
            L.group_chunk([{"task": "t"}], [])
            raise AssertionError("must raise SystemExit")
        except SystemExit as e:
            msg = str(e)
            assert "OPENAI_ENDPOINT" in msg and "401" in msg, msg
    finally:
        L.llm_json = orig
    print("test_learn regressions OK")


# pytest entry point (CI also runs this file as a script)
def test_all():
    run()
    run_regressions()


if __name__ == "__main__":
    run()
    run_regressions()
