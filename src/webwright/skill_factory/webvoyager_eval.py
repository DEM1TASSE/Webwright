"""Evaluate Webwright artifacts with the original WebVoyager outcome-judge protocol.

The official evaluator consumes the task, final response, and last k screenshots.  This adapter
keeps that protocol while reading Webwright's final-run layout and writing resumable JSONL records.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
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
    response_file = Path(run) / "final_response.txt"
    if response_file.is_file():
        value = response_file.read_text(encoding="utf-8", errors="replace").strip()
        if value:
            return value
    log = Path(run) / "final_script_log.txt"
    matches = []
    if log.is_file():
        for line in log.read_text(encoding="utf-8", errors="replace").replace("\\n", "\n").splitlines():
            match = FINAL_RE.match(line)
            if match and match.group(1).strip():
                matches.append(match.group(1).strip())
    if matches:
        return matches[-1]
    if log.is_file():
        text = log.read_text(encoding="utf-8", errors="replace").replace("\\n", "\n")
        blocks = list(re.finditer(
            r"(?ims)^\s*(?:step\s+\d+\s+)?(?:action:\s*)?final[ _]?(?:response|answer):\s*"
            r"(.+?)(?=^\s*step\s+\d+\s+(?:action|evidence):|\Z)", text,
        ))
        if blocks:
            return blocks[-1].group(1).strip()
    workspace = Path(run).parents[1]
    trajectory = workspace / "trajectory.json"
    try:
        payload = json.loads(trajectory.read_text(encoding="utf-8"))
        return str((payload.get("info") or {}).get("submission") or "")
    except (OSError, ValueError):
        return ""


def verdict_label(response: str) -> int | None:
    # Judges sometimes append the requested verdict to an explanatory sentence.
    # The protocol's final verdict token is authoritative regardless of layout.
    matches = list(
        re.finditer(
            r"(?i)(?:\*{1,2})?\bVERDICT:\s*(NOT SUCCESS|SUCCESS)"
            r"\s*(?:\*{1,2})?(?=$|[.!?])",
            response,
        )
    )
    if not matches:
        return None
    return int(matches[-1].group(1).upper() == "SUCCESS")


def evaluate_evidence(task_id, task, run, screenshots, answer, engine, mode=None,
                      repetitions=3, judge_mode="WebVoyager_original_protocol",
                      evaluation_date=None):
    """Judge an explicit evidence set.

    This is also used by composite-task evaluation: one browser run can be judged
    independently against each original WebVoyager instruction without inventing a
    new ground truth or collapsing partial completion into one opaque label.
    """
    screenshots = [str(path) for path in screenshots]
    evaluation_date = evaluation_date or datetime.now(timezone.utc).date().isoformat()
    content = [{"type": "text", "text": (
        f"EVALUATION DATE (UTC): {evaluation_date}\n"
        f"TASK: {task['task']}\nResult Response: {answer}\n"
        f"{len(screenshots)} screenshots from the trajectory follow."
    )}]
    content.extend({"type": "image_url", "image_url": path} for path in screenshots)
    content.append({"type": "text", "text": "Your verdict:"})
    responses, labels = [], []
    for _ in range(repetitions):
        response = engine.generate([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ], max_new_tokens=1200)[0]
        responses.append(response)
        labels.append(verdict_label(response))
    valid_labels = [label for label in labels if label in (0, 1)]
    majority = (int(sum(valid_labels) * 2 > len(valid_labels))
                if len(valid_labels) == repetitions else None)
    return {
        "task_id": task_id, "web_name": task.get("web_name"), "website": task["website"],
        "task": task["task"], "mode": mode, "judge_mode": judge_mode,
        "final_run_dir": str(run), "final_response": answer,
        "screenshot_paths": screenshots, "evaluation_responses": responses,
        "judge_labels": labels, "judge_model": engine.model,
        "judge_repetitions": repetitions, "aggregation": "majority_vote",
        "predicted_label": majority, "evaluation_date_utc": evaluation_date,
    }


def evaluate_task(task_id, task_dir, task, engine, mode=None, max_images=5, repetitions=3):
    newest = latest_run(task_dir)
    if newest is None:
        raise RuntimeError("no final_runs/run_* with artifacts")
    run_root = Path(task_dir) / "final_runs"
    candidates = sorted(
        (path for path in run_root.iterdir() if path.is_dir() and path.name.startswith("run_")),
        key=lambda path: int(path.name.rsplit("_", 1)[-1]), reverse=True,
    )
    run, screenshots, answer = None, [], ""
    for candidate in candidates:
        candidate_shots = load_screenshots(candidate / "screenshots")
        candidate_answer = load_final_response(candidate)
        if candidate_shots and candidate_answer:
            run, screenshots, answer = candidate, candidate_shots, candidate_answer
            break
    if run is None:
        raise RuntimeError(f"no judgeable final run under {run_root}")
    screenshots = screenshots[-max_images:]
    return evaluate_evidence(
        task_id, task, run, screenshots, answer, engine, mode=mode,
        repetitions=repetitions,
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Judge Webwright runs with WebVoyager's protocol.")
    p.add_argument("--trajectories-dir", required=True)
    p.add_argument("--tasks-file", required=True, help="Official WebVoyager JSONL.")
    p.add_argument("--output", required=True)
    p.add_argument("--model", default="gpt-4o")
    p.add_argument("--endpoint", default=os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1/responses"))
    p.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""))
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--max-images", type=int, default=5)
    p.add_argument("--repetitions", type=int, default=3)
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
                                       a.mode, a.max_images, a.repetitions)
            except Exception as exc:
                print(f"judge failed {task_id}: {exc}", file=os.sys.stderr)
                continue
            stream.write(json.dumps(record, ensure_ascii=False) + "\n"); stream.flush()
            print(f"{task_id}: predicted_label={record['predicted_label']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
