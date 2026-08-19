import importlib.util
import json
import os
from pathlib import Path

import pytest


_PATH = Path(__file__).parents[1] / "evals" / "webarena" / "webarena_final_state_eval.py"
_SPEC = importlib.util.spec_from_file_location("webarena_final_state_eval", _PATH)
E = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(E)

ORIGINAL_TASKS = Path(
    "/home/t-demiwang/project/Code-Web-Agent/webarena_test/dataset/test_raw.json"
)
DEPLOYMENT_CONFIG = Path("/home/t-demiwang/project/Code-Web-Agent/verified_config.json")
WEBARENA_ROOT = Path(os.environ.get("WEBARENA_ROOT", "/tmp/webarena-official-inspect"))


def test_validate_final_state_accepts_external_dom_file():
    assert E.validate_final_state({
        "final_url": "https://example.test/final",
        "html_path": "final_state.html",
        "document_status": 200,
        "answer": "",
    }) == []


def test_saved_dom_cannot_escape_run_directory(tmp_path):
    outside = tmp_path.parent / "outside.html"
    outside.write_text("<html></html>")
    state = tmp_path / "final_state.json"
    state.write_text(json.dumps({
        "final_url": "https://example.test/final",
        "html_path": "../outside.html",
        "document_status": 200,
        "answer": "",
    }))
    result = E.evaluate_saved_state(
        task_id=44, final_state_path=state, tasks_path=ORIGINAL_TASKS,
        deployment_config=DEPLOYMENT_CONFIG, webarena_root=WEBARENA_ROOT,
    )
    assert result["status"] == "invalid_final_state"
    assert "escapes" in result["errors"][0]


@pytest.mark.skipif(
    not (WEBARENA_ROOT / "evaluation_harness" / "evaluators.py").is_file(),
    reason="pinned official WebArena checkout unavailable",
)
def test_official_url_evaluator_scores_restored_final_url(tmp_path):
    environments = json.loads(DEPLOYMENT_CONFIG.read_text())["environments"]
    gitlab = environments["__GITLAB__"]["urls"][0].rstrip("/")
    state = tmp_path / "final_state.json"
    state.write_text(json.dumps({
        "final_url": gitlab + "/dashboard/todos",
        "html": "<html></html>",
        "document_status": 200,
        "answer": "",
    }))
    result = E.evaluate_saved_state(
        task_id=44, final_state_path=state, tasks_path=ORIGINAL_TASKS,
        deployment_config=DEPLOYMENT_CONFIG, webarena_root=WEBARENA_ROOT,
    )
    assert result["score"] == 1.0
    assert result["eval_types"] == ["url_match"]


@pytest.mark.skipif(
    not (WEBARENA_ROOT / "evaluation_harness" / "evaluators.py").is_file(),
    reason="pinned official WebArena checkout unavailable",
)
def test_official_program_html_evaluator_scores_restored_dom(tmp_path):
    (tmp_path / "final_state.html").write_text(
        "<html><body>Jaw Bruxism Mouth Guard</body></html>"
    )
    state = tmp_path / "final_state.json"
    state.write_text(json.dumps({
        "final_url": "https://example.test/product",
        "html_path": "final_state.html",
        "document_status": 200,
        "answer": "",
    }))
    result = E.evaluate_saved_state(
        task_id=118, final_state_path=state, tasks_path=ORIGINAL_TASKS,
        deployment_config=DEPLOYMENT_CONFIG, webarena_root=WEBARENA_ROOT,
    )
    assert result["score"] == 1.0
    assert result["eval_types"] == ["program_html"]
