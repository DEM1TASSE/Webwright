"""Evaluate Webwright artifacts with the original WebVoyager outcome-judge protocol.

The official evaluator consumes the task, final response, and last k screenshots.  This adapter
keeps that protocol while reading Webwright's final-run layout and writing resumable JSONL records.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from .om2w_eval import ResponsesEngine, discover_task_dirs, latest_run, load_screenshots


SYSTEM_PROMPT = """As an evaluator, you will receive a web task instruction, result screenshots,
and the agent's final response. Judge only whether all requirements are visibly or textually
completed. Do not interact with the website. Screenshots override a contradictory response, but a
response may contain details not visible in the screenshots. If any required subtask is missing,
the result is unsuccessful. Explain the decision briefly and end with exactly one line containing
VERDICT: SUCCESS or VERDICT: NOT SUCCESS."""

FINAL_RE = re.compile(r"^\s*final[ _]?(?:response|answer)\s*:\s*(.*)$", re.I)


def load_task_map(path: str | Path) -> dict[str, dict]:
    """Load official WebVoyager JSONL (or a JSON list) keyed by ``id``."""
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        value = json.loads(text)
        rows = value if isinstance(value, list) else value.get("tasks", [])
    out = {}
    for row in rows:
        task_id = row.get("id") or row.get("task_id")
        task = row.get("ques") or row.get("task") or row.get("task_description")
        website = row.get("web") or row.get("website")
        if task_id and task and website:
            out[str(task_id)] = {**row, "task_id": str(task_id), "task": str(task),
                                 "website": str(website)}
    return out


def load_final_response(run: str | Path) -> str:
    """Extract the last instrumented final response without depending on agent internals."""
    log = Path(run) / "final_script_log.txt"
    matches = []
    if log.is_file():
        for line in log.read_text(encoding="utf-8", errors="replace").replace("\\n", "\n").splitlines():
            match = FINAL_RE.match(line)
            if match:
                matches.append(match.group(1).strip())
    if matches:
        return matches[-1]
    workspace = Path(run).parents[1]
    trajectory = workspace / "trajectory.json"
    try:
        payload = json.loads(trajectory.read_text(encoding="utf-8"))
        return str((payload.get("info") or {}).get("submission") or "")
    except (OSError, ValueError):
        return ""


def verdict_label(response: str) -> int | None:
    matches = list(re.finditer(r"(?im)^\s*VERDICT:\s*(NOT SUCCESS|SUCCESS)\s*$", response))
    if not matches:
        return None
    return int(matches[-1].group(1).upper() == "SUCCESS")


def evaluate_task(task_id, task_dir, task, engine, mode=None, max_images=15):
    run = latest_run(task_dir)
    if run is None:
        raise RuntimeError("no final_runs/run_* with artifacts")
    screenshots = load_screenshots(run / "screenshots")
    if not screenshots:
        raise RuntimeError(f"no PNG screenshots in {run / 'screenshots'}")
    screenshots = screenshots[-max_images:]
    answer = load_final_response(run)
    if not answer:
        raise RuntimeError(f"no final response in {run}")
    content = [{"type": "text", "text": (
        f"TASK: {task['task']}\nResult Response: {answer}\n"
        f"{len(screenshots)} screenshots from the end of the trajectory follow."
    )}]
    content.extend({"type": "image_url", "image_url": path} for path in screenshots)
    content.append({"type": "text", "text": "Your verdict:"})
    response = engine.generate([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ], max_new_tokens=1200)[0]
    return {
        "task_id": task_id, "web_name": task.get("web_name"), "website": task["website"],
        "task": task["task"], "mode": mode, "judge_mode": "WebVoyager_original_protocol",
        "final_run_dir": str(run), "final_response": answer,
        "screenshot_paths": screenshots, "evaluation_response": response,
        "predicted_label": verdict_label(response),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Judge Webwright runs with WebVoyager's protocol.")
    p.add_argument("--trajectories-dir", required=True)
    p.add_argument("--tasks-file", required=True, help="Official WebVoyager JSONL.")
    p.add_argument("--output", required=True)
    p.add_argument("--model", default="gpt-4o")
    p.add_argument("--endpoint", default=os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1/responses"))
    p.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""))
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--max-images", type=int, default=15)
    p.add_argument("--mode", choices=("scratch", "routed"))
    a = p.parse_args(argv)
    if not a.api_key:
        raise SystemExit("set OPENAI_API_KEY or pass --api-key")
    tasks = load_task_map(a.tasks_file)
    task_dirs = discover_task_dirs(a.trajectories_dir, set(tasks))
    output = Path(a.output); output.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if output.exists():
        existing = {json.loads(line)["task_id"] for line in output.read_text().splitlines() if line.strip()}
    engine = ResponsesEngine(a.model, a.api_key, a.endpoint, a.timeout)
    with output.open("a", encoding="utf-8") as stream:
        for task_id in sorted(task_dirs):
            if task_id in existing:
                continue
            try:
                record = evaluate_task(task_id, task_dirs[task_id], tasks[task_id], engine,
                                       a.mode, a.max_images)
            except Exception as exc:
                print(f"judge failed {task_id}: {exc}", file=os.sys.stderr)
                continue
            stream.write(json.dumps(record, ensure_ascii=False) + "\n"); stream.flush()
            print(f"{task_id}: predicted_label={record['predicted_label']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

