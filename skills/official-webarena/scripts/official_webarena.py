#!/usr/bin/env python3
"""Inspect, run, and evaluate original WebArena tasks with Webwright."""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from webarena_final_state_eval import (
    OFFICIAL_COMMIT,
    evaluate_saved_state,
    load_task,
    resolve_placeholders,
)


FINAL_STATE_SPEC = r"""

## Required benchmark artifacts
This is an original WebArena benchmark task. Work only from the current goal and live website.
Immediately before closing the same live Playwright page, wait for it to settle and save:

1. `$WORKSPACE_DIR/final_state.html`: the exact result of `await page.content()`. For form tasks,
   first mirror current input values/checked state and selected options into the DOM without
   changing them, so serialization preserves live form state.
2. `$WORKSPACE_DIR/final_state.json`:
   {"final_url": page.url, "html_path": "final_state.html",
    "document_status": <integer HTTP status or null>,
    "answer": <concise textual answer, or "" for a pure navigation task>}
3. `$WORKSPACE_DIR/agent_response.json`:
   {"task_type": "RETRIEVE|NAVIGATE", "status": "SUCCESS|NOT_FOUND_ERROR",
    "retrieved_data": <JSON answer or null>, "error_details": null}

The URL and DOM must come from the same live page. Do not invent either artifact and do not use a
HAR as a substitute. If absence is proven, use textual answer `N/A`; otherwise do not infer absence
from one partial search or a failed endpoint.
"""


def load_deployment(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value.get("environments"), dict):
        raise ValueError(f"{path}: missing environments object")
    return value


def tasks_path(args) -> Path:
    return Path(args.tasks) if args.tasks else Path(args.webarena_root) / "config_files" / "test.raw.json"


def task_start_urls(task: dict) -> list[str]:
    urls = task.get("start_urls") or []
    if urls:
        return [str(url).strip() for url in urls if str(url).strip()]
    raw = task.get("start_url")
    if not isinstance(raw, str):
        return []
    # Original WebArena uses this delimiter when the official harness opens several tabs.
    return [part.strip() for part in raw.split(" |AND| ") if part.strip()]


def task_start_url(task: dict) -> str:
    urls = task_start_urls(task)
    return urls[0] if urls else ""


def unresolved_placeholders(value: str) -> list[str]:
    return sorted(set(re.findall(r"__[A-Z0-9_]+__", value)))


def credentials_for(task: dict, environments: dict) -> dict | None:
    raw_url = task_start_url(task)
    for placeholder, config in environments.items():
        if placeholder in raw_url and isinstance(config.get("credentials"), dict):
            return config["credentials"]
    sites = [str(site).upper() for site in task.get("sites") or []]
    for placeholder, config in environments.items():
        normalized = placeholder.strip("_").upper()
        if normalized in sites and isinstance(config.get("credentials"), dict):
            return config["credentials"]
    return None


def infer_task_type(task: dict) -> str:
    eval_types = set(task.get("eval", {}).get("eval_types") or [])
    return "RETRIEVE" if "string_match" in eval_types else "NAVIGATE"


def task_context(args) -> tuple[dict, Path, dict, str]:
    source = tasks_path(args)
    if not source.is_file():
        raise ValueError(f"original WebArena task file missing: {source}")
    task = load_task(source, args.task_id)
    if not task:
        raise ValueError(f"original WebArena task {args.task_id} missing from {source}")
    if not isinstance(task.get("eval"), dict):
        raise ValueError(f"task {args.task_id} does not have an original WebArena eval object")
    deployment = load_deployment(args.deployment_config)
    environments = deployment["environments"]
    resolved = resolve_placeholders(task, environments)
    resolved_urls = task_start_urls(resolved)
    start_url = resolved_urls[0] if resolved_urls else ""
    missing = unresolved_placeholders("\n".join(resolved_urls))
    if missing:
        raise ValueError(f"unresolved deployment placeholders: {', '.join(missing)}")
    if not start_url:
        raise ValueError(f"task {args.task_id} has no start URL")
    return task, source, deployment, start_url


def build_prompt(task: dict, deployment: dict, start_url: str) -> str:
    credentials = credentials_for(task, deployment["environments"])
    login = ""
    if credentials:
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        login = (
            f"\nIf authentication is required, use username `{username}` and "
            f"password `{password}`."
        )
    resolved_task = resolve_placeholders(task, deployment["environments"])
    start_urls = task_start_urls(resolved_task) or [start_url]
    if len(start_urls) == 1:
        start_note = f"Start URL: {start_urls[0]}"
    else:
        start_note = (
            "Start URLs (the official harness opens each in a separate tab):\n- "
            + "\n- ".join(start_urls)
            + "\nOpen every listed URL in its own tab before solving."
        )
    return (
        "Complete this web task.\n\n"
        f"Goal: {task['intent']}\n"
        f"{start_note}{login}\n"
        f"Expected task interface: {infer_task_type(task)}"
        + FINAL_STATE_SPEC
    )


def inspect_task(args) -> dict:
    task, source, deployment, start_url = task_context(args)
    resolved_task = resolve_placeholders(task, deployment["environments"])
    return {
        "task_id": args.task_id,
        "task_source": "official_webarena",
        "tasks_path": str(source.resolve()),
        "intent": task.get("intent"),
        "sites": task.get("sites") or [],
        "start_url": start_url,
        "start_urls": task_start_urls(resolved_task),
        "eval_types": task.get("eval", {}).get("eval_types") or [],
        "task_interface": infer_task_type(task),
        "credentials_available": credentials_for(task, deployment["environments"]) is not None,
        "official_webarena_commit": OFFICIAL_COMMIT,
    }


def find_run(output_dir: Path, key: str, before: set[Path]) -> Path | None:
    candidates = sorted(
        (path for path in output_dir.glob(f"{key}_*") if path.is_dir() and path not in before),
        key=lambda path: path.stat().st_mtime_ns,
    )
    return candidates[-1] if candidates else None


def complete_artifact_run(output_dir: Path, key: str, before: set[Path]) -> Path | None:
    run_dir = find_run(output_dir, key, before)
    if not run_dir:
        return None
    state_path = run_dir / "final_state.json"
    response_path = run_dir / "agent_response.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        response = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(state.get("final_url"), str) or not state["final_url"].strip():
        return None
    html_path = state.get("html_path")
    if not isinstance(html_path, str) or not (run_dir / html_path).is_file():
        return None
    if response.get("status") not in {"SUCCESS", "NOT_FOUND_ERROR"}:
        return None
    return run_dir


def terminate_process_group(process: subprocess.Popen) -> int:
    if process.poll() is not None:
        return int(process.returncode)
    os.killpg(process.pid, signal.SIGTERM)
    try:
        return process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        return process.wait()


def resolve_agent_python(explicit: str | None = None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser().absolute()
    else:
        local_venv = Path.cwd() / ".venv" / "bin" / "python"
        # Preserve the virtualenv symlink path. Resolving it selects the base interpreter and
        # silently loses the environment's site-packages.
        candidate = local_venv.absolute() if local_venv.is_file() else Path(sys.executable).absolute()
    if not candidate.is_file():
        raise ValueError(f"agent Python executable does not exist: {candidate}")
    return candidate


def agent_subprocess_env(python_executable: Path) -> dict[str, str]:
    """Keep agent-authored subprocesses in the same Python environment as Webwright."""
    executable = Path(python_executable).absolute()
    env = dict(os.environ)
    bin_dir = str(executable.parent)
    old_parts = [part for part in env.get("PATH", "").split(os.pathsep) if part]
    env["PATH"] = os.pathsep.join([bin_dir, *[part for part in old_parts if part != bin_dir]])
    env["VIRTUAL_ENV"] = str(executable.parent.parent)
    return env


def run_task(args) -> dict:
    task, source, deployment, start_url = task_context(args)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    key = f"official_webarena_task{args.task_id}"
    before = set(output_dir.glob(f"{key}_*"))
    configs = args.config or ["base.yaml", "model_openai.yaml"]
    agent_python = resolve_agent_python(args.python)
    command = [
        str(agent_python),
        "-m",
        "webwright.run.cli",
        "main",
        "-t",
        build_prompt(task, deployment, start_url),
        "--task-id",
        key,
        "--start-url",
        start_url,
        "-o",
        str(output_dir),
    ]
    for config in configs:
        command.extend(["-c", config])

    timed_out = False
    stopped_after_artifacts = False
    return_code = None
    process = subprocess.Popen(
        command,
        start_new_session=True,
        env=agent_subprocess_env(agent_python),
    )
    deadline = time.monotonic() + args.timeout
    run_dir = None
    while process.poll() is None:
        run_dir = complete_artifact_run(output_dir, key, before)
        if run_dir:
            stopped_after_artifacts = True
            return_code = terminate_process_group(process)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            return_code = terminate_process_group(process)
            break
        time.sleep(1)
    if return_code is None:
        return_code = process.returncode
    run_dir = run_dir or find_run(output_dir, key, before)
    final_state = run_dir / "final_state.json" if run_dir else None
    result = {
        "task_id": args.task_id,
        "task_source": "official_webarena",
        "tasks_path": str(source.resolve()),
        "agent_python": str(agent_python),
        "run_dir": str(run_dir) if run_dir else None,
        "return_code": return_code,
        "timed_out": timed_out,
        "stopped_after_artifacts": stopped_after_artifacts,
        "final_state_ready": bool(final_state and final_state.is_file()),
    }
    if run_dir:
        (run_dir / "official_webarena_run.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return result


def normalize_not_found(run_dir: Path) -> None:
    state_path = run_dir / "final_state.json"
    response_path = run_dir / "agent_response.json"
    if not state_path.is_file() or not response_path.is_file():
        return
    state = json.loads(state_path.read_text(encoding="utf-8"))
    response = json.loads(response_path.read_text(encoding="utf-8"))
    if response.get("status") != "NOT_FOUND_ERROR" or state.get("answer") == "N/A":
        return
    backup = run_dir / "final_state.agent.json"
    if not backup.exists():
        backup.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state["answer"] = "N/A"
    state["artifact_normalizations"] = ["not_found_status_to_official_na_v1"]
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def evaluate_task(args, run_dir: str | Path | None = None) -> dict:
    _, source, _, _ = task_context(args)
    run_path = Path(run_dir or args.run_dir).resolve()
    state_path = run_path / "final_state.json"
    if not state_path.is_file():
        return {
            "score": None,
            "status": "invalid_final_state",
            "task_id": args.task_id,
            "errors": [f"missing final state: {state_path}"],
        }
    normalize_not_found(run_path)
    result = evaluate_saved_state(
        task_id=args.task_id,
        final_state_path=state_path,
        tasks_path=source,
        deployment_config=args.deployment_config,
        webarena_root=args.webarena_root,
        model_config=args.model_config,
    )
    output = Path(args.output).resolve() if args.output else run_path / "official_webarena_eval.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["evaluation_path"] = str(output)
    return result


def pipeline(args) -> dict:
    run_result = run_task(args)
    if not run_result["final_state_ready"]:
        return {"run": run_result, "evaluation": None}
    evaluation = evaluate_task(args, run_result["run_dir"])
    return {"run": run_result, "evaluation": evaluation}


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", required=True, type=int)
    parser.add_argument("--webarena-root", required=True)
    parser.add_argument("--tasks")
    parser.add_argument("--deployment-config", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect")
    add_common(inspect_parser)

    run_parser = commands.add_parser("run")
    add_common(run_parser)
    run_parser.add_argument("--output-dir", required=True)
    run_parser.add_argument("--config", action="append")
    run_parser.add_argument("--python", help="Python executable containing Webwright")
    run_parser.add_argument("--timeout", type=int, default=900)

    eval_parser = commands.add_parser("evaluate")
    add_common(eval_parser)
    eval_parser.add_argument("--run-dir", required=True)
    eval_parser.add_argument("--model-config")
    eval_parser.add_argument("--output")

    pipeline_parser = commands.add_parser("pipeline")
    add_common(pipeline_parser)
    pipeline_parser.add_argument("--output-dir", required=True)
    pipeline_parser.add_argument("--config", action="append")
    pipeline_parser.add_argument("--python", help="Python executable containing Webwright")
    pipeline_parser.add_argument("--timeout", type=int, default=900)
    pipeline_parser.add_argument("--model-config")
    pipeline_parser.add_argument("--output")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        result = inspect_task(args)
    elif args.command == "run":
        result = run_task(args)
    elif args.command == "evaluate":
        result = evaluate_task(args)
    else:
        result = pipeline(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "evaluate":
        return 0 if result.get("score") is not None else 2
    if args.command == "pipeline" and result.get("evaluation") is not None:
        return 0 if result["evaluation"].get("score") is not None else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
