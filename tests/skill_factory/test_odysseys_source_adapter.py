import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
ODYSSEYS = ROOT / "evals/odysseys"
sys.path.insert(0, str(ODYSSEYS))
SPEC = importlib.util.spec_from_file_location("odysseys_source_adapter",
                                              ODYSSEYS / "adapt_source_run.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_discovers_sites_and_maps_reddit_frontend(tmp_path):
    run = tmp_path / "run"
    (run / "screenshots").mkdir(parents=True)
    (run / "final_script_log.txt").write_text(
        "step 1 https://safereddit.com/r/test/comments/1/x\n"
        "step 2 https://www.cnn.com/story\n")
    (run / "final_script.py").write_text(
        'reddit_url = "https://safereddit.com/r/test/comments/1/x"\n'
        'cnn_url = "https://www.cnn.com/story"\n')
    (run / "screenshots" / "final_reddit_thread.png").write_bytes(b"png")
    evidence = MODULE.discover_site_evidence(run)
    assert set(evidence) == {"reddit_com", "cnn_com"}
    assert evidence["reddit_com"]["screenshots"]
    assert "reddit_url" in evidence["reddit_com"]["code_excerpt"]
    assert MODULE.site_for_url("https://embed.reddit.com/r/x") == "reddit_com"
    assert MODULE.site_for_url("https://2.boredpanda.com/x") == "boredpanda_com"


def test_adapter_requires_review_and_passing_rubric(tmp_path):
    run = tmp_path / "run"
    (run / "screenshots").mkdir(parents=True)
    (run / "final_script_log.txt").write_text(
        "opened https://reddit.com/r/test/comments/1/x\n")
    (run / "final_script.py").write_text('url="https://reddit.com/r/test/comments/1/x"\n')
    judge = tmp_path / "judge.json"
    judge.write_text(json.dumps({"tasks": [{"task_id": "t", "rubric_scores": {"R1": 1}}]}))
    task = {"task_id": "t", "rubrics": {"R1": {
        "requirement": "Open the Reddit thread", "verification": "See Reddit",
    }}}
    pending = MODULE.adapt(task, run, judge, tmp_path / "pending")
    assert pending["segments"][0]["review_status"] == "needs_review"
    assert pending["segments"][0]["admitted"] is False
    approved = MODULE.adapt(task, run, judge, tmp_path / "approved", approvals={
        "reddit_com": {"review_status": "approved", "rubric_ids": ["R1"],
                       "template_id": "reddit.thread.open", "goal": "open thread"},
    })
    assert approved["segments"][0]["admitted"] is True


def test_failed_rubric_cannot_be_admitted(tmp_path):
    run = tmp_path / "run"
    (run / "screenshots").mkdir(parents=True)
    (run / "final_script_log.txt").write_text("https://reddit.com/r/x\n")
    (run / "final_script.py").write_text('url="https://reddit.com/r/x"\n')
    judge = tmp_path / "judge.json"
    judge.write_text(json.dumps({"tasks": [{"task_id": "t", "rubric_scores": {"R1": 0}}]}))
    result = MODULE.adapt({"task_id": "t", "rubrics": {}}, run, judge, tmp_path / "out",
                          approvals={"reddit_com": {"review_status": "approved",
                          "rubric_ids": ["R1"], "template_id": "reddit.list"}})
    assert result["segments"][0]["admitted"] is False
