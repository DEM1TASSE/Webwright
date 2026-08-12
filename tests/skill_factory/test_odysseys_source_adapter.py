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


def test_google_maps_urls_are_evidence_but_google_search_is_not():
    assert MODULE.site_for_url("https://www.google.com/maps/dir/A/B") == "google_maps"
    assert MODULE.site_for_url("https://maps.google.com/?q=A") == "google_maps"
    assert MODULE.site_for_url("https://www.google.com/search?q=A") is None


def test_site_excerpt_traces_url_constant_into_playwright_page_block(tmp_path):
    run = tmp_path / "run"
    (run / "screenshots").mkdir(parents=True)
    (run / "final_script_log.txt").write_text(
        "YouTube URL: https://www.youtube.com/watch?v=abc\n")
    (run / "final_script.py").write_text(
        'YT_URL = "https://www.youtube.com/watch?v=abc"\n'
        'OTHER_URL = "https://example.com/item"\n'
        'async def main():\n'
        '    yt = await context.new_page()\n'
        '    await yt.goto(YT_URL)\n'
        '    await yt.keyboard.press("k")\n'
        '    await snap(yt, "youtube_playing.png")\n'
        '    other = await context.new_page()\n'
        '    await other.goto(OTHER_URL)\n')
    evidence = MODULE.discover_site_evidence(run)
    excerpt = evidence["youtube_com"]["code_excerpt"]
    assert 'await yt.goto(YT_URL)' in excerpt
    assert 'await yt.keyboard.press("k")' in excerpt
    assert 'await other.goto(OTHER_URL)' not in excerpt


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


def test_approved_code_ranges_replace_heuristic_excerpt(tmp_path):
    run = tmp_path / "run"
    (run / "screenshots").mkdir(parents=True)
    (run / "final_script_log.txt").write_text("https://reddit.com/r/test\n")
    (run / "final_script.py").write_text(
        'URL = "https://reddit.com/r/test"\n'
        'page = await context.new_page()\n'
        'await page.goto(URL)\n'
        'await page.click("article")\n')
    judge = tmp_path / "judge.json"
    judge.write_text(json.dumps({"tasks": [{"task_id": "t", "rubric_scores": {"R1": 1}}]}))
    task = {"task_id": "t", "rubrics": {"R1": {"requirement": "Reddit"}}}
    result = MODULE.adapt(task, run, judge, tmp_path / "out", approvals={
        "reddit_com": {"review_status": "approved", "rubric_ids": ["R1"],
                       "template_id": "reddit.open", "code_ranges": [[2, 4]]},
    })
    segment = result["segments"][0]
    assert segment["code_ranges"] == [(2, 4)]
    assert 'await page.click("article")' in Path(segment["code_path"]).read_text()
    assert 'URL = "https://reddit.com/r/test"' not in Path(segment["code_path"]).read_text()


def test_completed_run_accepts_workspace_level_final_script(tmp_path):
    workspace = tmp_path / "workspace"
    run = workspace / "final_runs" / "run_1"
    run.mkdir(parents=True)
    (workspace / "final_script.py").write_text("print('executed')\n")
    (run / "final_script_log.txt").write_text("done\n")
    (run / "self_reflect_result.json").write_text(json.dumps({"predicted_label": 0}))
    assert MODULE.completed_run(workspace) == run
    assert MODULE.source_script(run) == workspace / "final_script.py"


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
