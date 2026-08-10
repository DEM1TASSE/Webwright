"""Run upstream Online-Mind2Web WebJudge directly on Webwright run artifacts.

The official evaluator is imported from a separately-cloned Online-Mind2Web repository. This
adapter owns only the artifact bridge: task text, factual action log, screenshots, and JSONL output.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import importlib
import json
import mimetypes
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

FINAL_RUN_RE = re.compile(r"run_(\d+)$", re.IGNORECASE)
FINAL_RESPONSE_RE = re.compile(r"^\s*final[ _]?(?:response|answer)\s*:", re.IGNORECASE)
SCREENSHOT_RE = re.compile(r"^final_execution_(\d+).*\.png$", re.IGNORECASE)


def load_task_map(path: str | Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("tasks", [])
    return {
        str(row["task_id"]): str(
            row.get("confirmed_task") or row.get("task_description") or row.get("task")
        )
        for row in rows
        if isinstance(row, dict) and row.get("task_id") and (
            row.get("confirmed_task") or row.get("task_description") or row.get("task")
        )
    }


def discover_task_dirs(root: str | Path, task_ids: set[str]) -> dict[str, Path]:
    """Resolve the newest Webwright workspace for every task."""
    found: dict[str, list[Path]] = {}
    for child in Path(root).iterdir():
        if not child.is_dir():
            continue
        task_id = None
        metadata = child / "task.json"
        if metadata.is_file():
            try:
                task_id = str(json.loads(metadata.read_text(encoding="utf-8")).get("task_id") or "")
            except (OSError, ValueError):
                pass
        if not task_id and child.name in task_ids:
            task_id = child.name
        if task_id in task_ids:
            found.setdefault(task_id, []).append(child)
    return {
        task_id: max(paths, key=lambda path: (path.stat().st_mtime_ns, path.name))
        for task_id, paths in found.items()
    }


def latest_run(task_dir: str | Path) -> Path | None:
    root = Path(task_dir) / "final_runs"
    candidates = []
    if root.is_dir():
        for child in root.iterdir():
            match = FINAL_RUN_RE.fullmatch(child.name) if child.is_dir() else None
            if match and ((child / "final_script_log.txt").is_file() or (child / "screenshots").is_dir()):
                candidates.append((int(match.group(1)), child))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def load_actions(path: str | Path) -> list[str]:
    source = Path(path)
    if not source.is_file():
        return []
    actions = []
    for line in source.read_text(encoding="utf-8", errors="replace").replace("\\n", "\n").splitlines():
        line = line.strip()
        if line and not FINAL_RESPONSE_RE.match(line):
            actions.append(line)
    return actions


def load_screenshots(path: str | Path) -> list[str]:
    root = Path(path)
    if not root.is_dir():
        return []

    def key(p: Path) -> tuple[int, int, str]:
        canonical = SCREENSHOT_RE.match(p.name)
        if canonical:
            return (0, int(canonical.group(1)), p.name.lower())
        other = re.match(r"^(?:cp|critical_point_)?(\d+)", p.name, re.IGNORECASE)
        return (1, int(other.group(1)) if other else 10**9, p.name.lower())

    return [str(p) for p in sorted(root.glob("*.png"), key=key)]


def _data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return f"data:{mime or 'image/png'};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


class ResponsesEngine:
    """Small compatibility engine for the upstream evaluator's ``model.generate`` contract."""

    def __init__(self, model: str, api_key: str, endpoint: str, timeout: int = 600):
        self.model, self.api_key, self.endpoint, self.timeout = model, api_key, endpoint, timeout

    def generate(self, messages: list[dict[str, Any]], max_new_tokens: int = 8192) -> list[str]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("OM2W evaluation requires the project's httpx dependency") from exc
        serialized = []
        for message in messages:
            role = "developer" if message.get("role") == "system" else message.get("role", "user")
            raw = message.get("content", "")
            raw_parts = [{"type": "text", "text": raw}] if isinstance(raw, str) else raw
            parts = []
            for part in raw_parts:
                if part.get("type") in ("text", "input_text"):
                    parts.append({"type": "input_text", "text": str(part.get("text", ""))})
                elif part.get("type") in ("image_url", "input_image"):
                    image = part.get("image_url", "")
                    url = image.get("url", "") if isinstance(image, dict) else image
                    if url and not str(url).startswith("data:") and Path(str(url)).is_file():
                        url = _data_url(Path(str(url)))
                    parts.append({"type": "input_image", "image_url": url, "detail": "high"})
            serialized.append({"type": "message", "role": role, "content": parts})
        response = httpx.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": serialized, "max_output_tokens": max_new_tokens},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        text = payload.get("output_text")
        if not text:
            text = "\n".join(
                str(part.get("text", ""))
                for item in payload.get("output", []) if item.get("type") == "message"
                for part in item.get("content", []) if part.get("type") in ("output_text", "text")
            )
        return [str(text or "")]


def _label(response: str) -> int | None:
    matches = list(re.finditer(r"(?i)status:\s*[\"']?(success|failure)", response))
    return None if not matches else int(matches[-1].group(1).lower() == "success")


def import_upstream(src: str | Path):
    src = Path(src).resolve()
    if not (src / "methods" / "webjudge_online_mind2web.py").is_file():
        raise SystemExit(f"not an Online-Mind2Web src directory: {src}")
    sys.path.insert(0, str(src))
    try:
        return importlib.import_module("methods.webjudge_online_mind2web")
    except Exception as exc:
        raise SystemExit(f"could not import upstream WebJudge from {src}: {exc}") from exc


def evaluate_task(task_id: str, task_dir: Path, task: str, upstream, engine, threshold: int,
                  mode: str | None = None) -> dict:
    run = latest_run(task_dir)
    if run is None:
        raise RuntimeError("no final_runs/run_* with artifacts")
    actions = load_actions(run / "final_script_log.txt")
    screenshots = load_screenshots(run / "screenshots")
    if not screenshots:
        raise RuntimeError(f"no PNG screenshots in {run / 'screenshots'}")
    messages, text, system, records, key_points = asyncio.run(
        upstream.WebJudge_Online_Mind2Web_eval(task, actions, screenshots, engine, threshold)
    )
    response = engine.generate(messages, max_new_tokens=8192)[0]
    return {
        "task_id": task_id,
        "mode": mode,
        "judge_mode": "WebJudge_Online_Mind2Web_eval",
        "final_run_dir": str(run),
        "action_history": actions,
        "sandbox_screenshot_paths": screenshots,
        "image_judge_record": records,
        "key_points": key_points,
        "input_text": text,
        "system_msg": system,
        "evaluation_details": {"response": response, "predicted_label": _label(response)},
        "predicted_label": _label(response),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Evaluate Webwright artifacts with upstream OM2W WebJudge.")
    p.add_argument("--trajectories-dir", required=True)
    p.add_argument("--tasks-file", required=True, help="OM2W JSON containing task_id + confirmed_task/task.")
    p.add_argument("--upstream-src", required=True, help="Path to Online-Mind2Web/src.")
    p.add_argument("--output", required=True, help="Output JSONL file.")
    p.add_argument("--model", default="o4-mini")
    p.add_argument("--endpoint", default=os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1/responses"))
    p.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""))
    p.add_argument("--score-threshold", type=int, default=3)
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--mode", choices=("scratch", "routed"),
                   help="Optional experiment arm recorded in every verdict.")
    a = p.parse_args(argv)
    if not a.api_key:
        raise SystemExit("set OPENAI_API_KEY or pass --api-key")
    upstream = import_upstream(a.upstream_src)
    tasks = load_task_map(a.tasks_file)
    root, output = Path(a.trajectories_dir), Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if output.exists():
        existing = {json.loads(line)["task_id"] for line in output.read_text().splitlines() if line.strip()}
    task_dirs = discover_task_dirs(root, set(tasks))
    work = [(task_id, task_dirs[task_id]) for task_id in sorted(task_dirs)
            if task_id not in existing]

    def one(item):
        task_id, task_dir = item
        engine = ResponsesEngine(a.model, a.api_key, a.endpoint, a.timeout)
        return evaluate_task(
            task_id, task_dir, tasks[task_id], upstream, engine, a.score_threshold, a.mode
        )

    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        futures = {pool.submit(one, item): item[0] for item in work}
        for future in as_completed(futures):
            task_id = futures[future]
            try:
                record = future.result()
            except Exception as exc:
                print(f"judge failed {task_id}: {exc}", file=sys.stderr)
                continue
            with output.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{task_id}: predicted_label={record['predicted_label']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
