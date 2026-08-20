#!/usr/bin/env python3
"""Generate, clean-replay, and officially score a small AWS WebArena mutate pilot."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
REPO = EVALS.parents[1]
# Deployment access is environment-driven: this script keeps no machine-specific paths and
# no credentials, so it runs against any WebArena deployment. require_env() checks them.
WEBARENA_HOST = os.environ.get("WEBARENA_SSH_HOST", "")
SSH_USER = os.environ.get("WEBARENA_SSH_USER", "ubuntu")
SSH_KEY = os.environ.get("WEBARENA_SSH_KEY", "")
MYSQL_USER = os.environ.get("WEBARENA_MYSQL_USER", "magentouser")
MYSQL_PASSWORD = os.environ.get("WEBARENA_MYSQL_PASSWORD", "")
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
       "-i", SSH_KEY, f"{SSH_USER}@{WEBARENA_HOST}"]


def require_env() -> None:
    """Fail before touching the deployment if access is not configured."""
    missing = [name for name, value in (
        ("WEBARENA_SSH_HOST", WEBARENA_HOST),
        ("WEBARENA_SSH_KEY", SSH_KEY),
        ("WEBARENA_MYSQL_PASSWORD", MYSQL_PASSWORD),
    ) if not value]
    if missing:
        raise SystemExit(
            "missing required environment variables: " + ", ".join(missing) + "\n"
            "  export WEBARENA_SSH_HOST=<deployment host>\n"
            "  export WEBARENA_SSH_KEY=<path to the ssh private key>\n"
            "  export WEBARENA_MYSQL_PASSWORD=<site container's MySQL password>\n"
            "  # optional: WEBARENA_SSH_USER (default ubuntu), "
            "WEBARENA_MYSQL_USER (default magentouser)")

SITE = {
    "shopping": {
        "container": "shopping", "image": "shopping_final_0712",
        "port": "7770:80", "health": f"http://{WEBARENA_HOST}:7770/", "command": "",
    },
    "shopping_admin": {
        "container": "shopping_admin", "image": "shopping_admin_final_0719",
        "port": "7780:80", "health": f"http://{WEBARENA_HOST}:7780/admin", "command": "",
    },
    "reddit": {
        "container": "forum", "image": "postmill-populated-exposed-withimg",
        "port": "9999:80", "health": f"http://{WEBARENA_HOST}:9999/", "command": "",
    },
    "gitlab": {
        "container": "gitlab", "image": "gitlab-populated-final-port8023",
        "port": "8023:8023", "health": f"http://{WEBARENA_HOST}:8023/",
        "command": "/opt/gitlab/embedded/bin/runsvdir-start",
    },
}

TASK_IDS = [389, 399, 404, 409, 460, 467, 472, 501, 516, 663]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


HTTP = build_opener(_NoRedirect)

FINAL_SPEC = """

This is a state-changing MUTATE task. The deliverable is a deterministic standalone
`final_script.py`, not the exploratory trajectory.

Hard requirements:
- Perform the requested mutation exactly once. Do not apply a relative update twice.
- In the script, resolve output root as
  `Path(os.environ.get("WORKSPACE_DIR", Path(__file__).resolve().parent))`.
- After the mutation, use the same authenticated Playwright context to open or remain on the
  strongest page that visibly proves the requested final state.
- Immediately before closing, save `await page.content()` to
  `$WORKSPACE_DIR/final_state.html`, save the context authentication with
  `await context.storage_state(path="$WORKSPACE_DIR/storage_state.json")`, and write
  `$WORKSPACE_DIR/final_state.json` as
  {"final_url": page.url, "html_path": "final_state.html",
   "storage_state_path": "storage_state.json", "document_status": null, "answer": ""}.
- Write `$WORKSPACE_DIR/agent_response.json` as
  {"task_type":"MUTATE","status":"SUCCESS","retrieved_data":null,
   "error_details":null} only after the mutation and evidence capture complete.
- Run final_script.py once to validate it. After those artifacts exist, do not edit or run it
  again; declare completion immediately. Do not invoke self_reflection.
"""


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def http_status(url: str) -> int | None:
    try:
        with HTTP.open(Request(url, headers={"User-Agent": "webwright-mutate-pilot"}), timeout=10) as response:
            return int(response.status)
    except HTTPError as error:
        return int(error.code)
    except (URLError, TimeoutError, OSError):
        return None


def reset_site(site: str, *, timeout: int = 480) -> dict:
    spec = SITE[site]
    command = (
        "set -eu; "
        f"docker stop -t 90 {spec['container']} >/dev/null 2>&1 || true; "
        f"docker rm -f {spec['container']} >/dev/null 2>&1 || true; "
        f"docker run -d --name {spec['container']} -p {spec['port']} {spec['image']} "
        f"{spec['command']}"
    )
    started = time.monotonic()
    proc = subprocess.run([*SSH, command], text=True, capture_output=True, timeout=180)
    if proc.returncode:
        return {"ok": False, "phase": "docker_recreate", "returncode": proc.returncode,
                "stderr": proc.stderr[-2000:], "seconds": round(time.monotonic() - started, 1)}
    rewrite_attempts = 0
    if site in {"shopping", "shopping_admin"}:
        public_port = spec["port"].split(":", 1)[0]
        base_url = f"http://{WEBARENA_HOST}:{public_port}/"
        rewrite = (
            f"docker exec {spec['container']} mysql -u {MYSQL_USER} -p{MYSQL_PASSWORD} magentodb "
            "-e 'UPDATE core_config_data SET value=\""
            f"{base_url}"
            "\" WHERE path IN (\"web/secure/base_url\",\"web/unsecure/base_url\");' "
            f"&& docker exec {spec['container']} php /var/www/magento2/bin/magento cache:flush"
        )
        rewrite_deadline = time.monotonic() + 180
        while time.monotonic() < rewrite_deadline:
            rewrite_attempts += 1
            configured = subprocess.run([*SSH, rewrite], text=True, capture_output=True,
                                        timeout=90)
            if configured.returncode == 0:
                break
            time.sleep(10)
        else:
            return {"ok": False, "phase": "base_url_rewrite_timeout",
                    "attempts": rewrite_attempts, "stderr": configured.stderr[-2000:],
                    "seconds": round(time.monotonic() - started, 1)}
    observations = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = http_status(spec["health"])
        observations.append(status)
        if status in {200, 301, 302}:
            return {"ok": True, "phase": "healthy", "http_status": status,
                    "polls": len(observations), "rewrite_attempts": rewrite_attempts,
                    "seconds": round(time.monotonic() - started, 1)}
        time.sleep(10)
    return {"ok": False, "phase": "health_timeout", "observations": observations,
            "seconds": round(time.monotonic() - started, 1)}


def newest_run(runs: Path, key: str) -> Path | None:
    matches = sorted(runs.glob(f"{key}_*"))
    return matches[-1] if matches else None


def complete_artifact_dir(run_dir: Path | None) -> Path | None:
    if run_dir is None:
        return None
    candidates = [run_dir]
    final_runs = run_dir / "final_runs"
    if final_runs.is_dir():
        candidates.extend(sorted((path for path in final_runs.iterdir() if path.is_dir()),
                                 key=lambda path: path.stat().st_mtime, reverse=True))
    for candidate in candidates:
        for name in ("final_state.json", "final_state.html", "storage_state.json",
                     "agent_response.json"):
            if not (candidate / name).is_file():
                break
        else:
            try:
                response = load(candidate / "agent_response.json")
            except (OSError, ValueError):
                continue
            if response.get("task_type") == "MUTATE" and response.get("status") == "SUCCESS":
                return candidate
    return None


def complete_generation(run_dir: Path | None) -> bool:
    return complete_artifact_dir(run_dir) is not None


def stop_group(proc: subprocess.Popen, grace: int = 20) -> None:
    if proc.poll() is not None:
        return
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def generate(task: dict, config: dict, output: Path, model_config: Path,
             python: Path, timeout: int) -> dict:
    site = task["sites"][0]
    placeholder = {
        "gitlab": "__GITLAB__", "shopping": "__SHOPPING__",
        "shopping_admin": "__SHOPPING_ADMIN__", "reddit": "__REDDIT__",
    }[site]
    env_spec = config["environments"][placeholder]
    start_url = task["start_url"].replace(placeholder, env_spec["urls"][0].rstrip("/"))
    credentials = env_spec.get("credentials") or {}
    login = (f"\nIf login is required, use username `{credentials.get('username', '')}` "
             f"and password `{credentials.get('password', '')}`.")
    prompt = (f"Complete this WebArena task.\n\nGoal: {task['intent']}\n"
              f"Start URL: {start_url}{login}{FINAL_SPEC}")
    runs = output / "generation_runs" / site
    runs.mkdir(parents=True, exist_ok=True)
    key = f"task{task['task_id']}_mutate_pilot"
    command = [str(python), "-m", "webwright.run.cli", "main", "-t", prompt,
               "--task-id", key, "--start-url", start_url, "-o", str(runs),
               "-c", "base.yaml", "-c", str(model_config),
               "-c", str(EVALS / "model.eval.yaml")]
    log = output / "logs" / f"task{task['task_id']}.generation.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.Popen(command, cwd=REPO, env=os.environ.copy(), stdout=handle,
                                stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + timeout
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(5)
            if complete_generation(newest_run(runs, key)):
                stop_group(proc)
                handle.write("\nSTOPPED_AFTER_COMPLETE_MUTATE_ARTIFACT\n")
                break
        if proc.poll() is None:
            timed_out = True
            stop_group(proc)
            handle.write("\nGENERATION_TIMEOUT\n")
    run_dir = newest_run(runs, key)
    artifact_dir = complete_artifact_dir(run_dir)
    frozen = output / "frozen_scripts" / f"task{task['task_id']}" / "final_script.py"
    script_source = None
    if run_dir and (run_dir / "final_script.py").is_file():
        script_source = run_dir / "final_script.py"
    elif artifact_dir and (artifact_dir / "final_script.py").is_file():
        script_source = artifact_dir / "final_script.py"
    if script_source:
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(script_source, frozen)
    return {"ok": frozen.is_file(), "timed_out": timed_out, "returncode": proc.returncode,
            "seconds": round(time.monotonic() - started, 1),
            "run_dir": str(run_dir) if run_dir else None,
            "artifact_dir": str(artifact_dir) if artifact_dir else None,
            "frozen_script": str(frozen)}


def replay_and_score(task: dict, output: Path, config_path: Path, tasks_path: Path,
                     webarena_root: Path, model_config: Path, python: Path,
                     timeout: int) -> dict:
    replay = output / "replays" / f"task{task['task_id']}"
    if replay.exists():
        shutil.rmtree(replay)
    replay.mkdir(parents=True)
    frozen = output / "frozen_scripts" / f"task{task['task_id']}" / "final_script.py"
    script = replay / "final_script.py"
    shutil.copy2(frozen, script)
    env = dict(os.environ, WORKSPACE_DIR=str(replay),
               FINAL_RUN_DIR=str(replay / "final_runs" / "run_001"))
    started = time.monotonic()
    try:
        proc = subprocess.run([str(python), str(script)], cwd=replay, env=env,
                              text=True, capture_output=True, timeout=timeout)
        replay_status = "completed" if proc.returncode == 0 else "process_error"
        returncode = proc.returncode
        stdout, stderr = proc.stdout[-5000:], proc.stderr[-5000:]
    except subprocess.TimeoutExpired as error:
        replay_status = "timeout"
        returncode = None
        stdout = (error.stdout or "")[-5000:] if isinstance(error.stdout, str) else ""
        stderr = (error.stderr or "")[-5000:] if isinstance(error.stderr, str) else ""
    artifacts = {name: (replay / name).is_file() for name in (
        "agent_response.json", "final_state.json", "final_state.html", "storage_state.json",
    )}
    evaluation = None
    if replay_status == "completed" and all(artifacts.values()):
        eval_output = replay / "official_eval.json"
        command = [str(python), str(EVALS / "webarena_final_state_eval.py"),
                   "--task-id", str(task["task_id"]),
                   "--final-state", str(replay / "final_state.json"),
                   "--tasks", str(tasks_path), "--deployment-config", str(config_path),
                   "--webarena-root", str(webarena_root), "--model-config", str(model_config),
                   "--output", str(eval_output)]
        scored = subprocess.run(command, cwd=REPO, text=True, capture_output=True, timeout=300)
        if eval_output.is_file():
            evaluation = load(eval_output)
        else:
            evaluation = {"score": None, "status": "evaluator_process_error",
                          "returncode": scored.returncode,
                          "stderr": scored.stderr[-3000:], "stdout": scored.stdout[-3000:]}
    return {"status": replay_status, "returncode": returncode,
            "seconds": round(time.monotonic() - started, 1), "artifacts": artifacts,
            "stdout_tail": stdout, "stderr_tail": stderr, "evaluation": evaluation,
            "replay_dir": str(replay)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--webarena-root", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "artifacts")
    parser.add_argument("--generation-timeout", type=int, default=900)
    parser.add_argument("--replay-timeout", type=int, default=360)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--reuse-frozen", action="store_true")
    parser.add_argument("--task-ids", nargs="+", type=int, default=TASK_IDS)
    args = parser.parse_args()
    require_env()
    args.output = args.output.resolve()
    tasks = {row["task_id"]: row for row in load(args.tasks)}
    selected = [tasks[task_id] for task_id in args.task_ids]
    config = load(args.config)
    by_site = defaultdict(list)
    for task in selected:
        by_site[task["sites"][0]].append(task)
    args.output.mkdir(parents=True, exist_ok=True)

    def lane(site: str, rows: list[dict]):
        records = []
        for task in rows:
            record = {"task_id": task["task_id"], "site": site, "intent": task["intent"]}
            frozen = args.output / "frozen_scripts" / f"task{task['task_id']}" / "final_script.py"
            if args.reuse_frozen and frozen.is_file():
                record["pre_generation_reset"] = {"ok": True, "phase": "skipped_reuse"}
                record["generation"] = {
                    "ok": True, "reused": True, "frozen_script": str(frozen),
                }
            else:
                record["pre_generation_reset"] = reset_site(site)
                if not record["pre_generation_reset"]["ok"]:
                    record["status"] = "reset_failed"
                    records.append(record)
                    save(args.output / "results" / f"task{task['task_id']}.json", record)
                    continue
                record["generation"] = generate(
                    task, config, args.output, args.model_config, args.python,
                    args.generation_timeout,
                )
            if not record["generation"]["ok"]:
                record["status"] = "generation_failed"
                records.append(record)
                save(args.output / "results" / f"task{task['task_id']}.json", record)
                continue
            record["pre_replay_reset"] = reset_site(site)
            if not record["pre_replay_reset"]["ok"]:
                record["status"] = "reset_failed"
                records.append(record)
                save(args.output / "results" / f"task{task['task_id']}.json", record)
                continue
            record["replay"] = replay_and_score(
                task, args.output, args.config, args.tasks, args.webarena_root,
                args.model_config, args.python, args.replay_timeout,
            )
            record["status"] = "complete"
            records.append(record)
            save(args.output / "results" / f"task{task['task_id']}.json", record)
        cleanup = reset_site(site)
        save(args.output / "results" / f"_{site}_cleanup.json", cleanup)
        return records

    all_records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(lane, site, rows) for site, rows in by_site.items()]
        for future in concurrent.futures.as_completed(futures):
            rows = future.result()
            all_records.extend(rows)
            for row in rows:
                print(json.dumps({"task_id": row["task_id"], "site": row["site"],
                                  "status": row["status"],
                                  "score": ((row.get("replay") or {}).get("evaluation") or {}).get("score")},
                                 ensure_ascii=False), flush=True)
    save(args.output / "summary.json", {"tasks": sorted(all_records, key=lambda x: x["task_id"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
