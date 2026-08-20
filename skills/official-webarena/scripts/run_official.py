#!/usr/bin/env python3
"""Lane runner over the official-webarena skill pipeline. Resumable, bounded concurrency.

Each job shells out to skills/official-webarena/scripts/official_webarena.py pipeline, which
runs Webwright, waits for the three final artifacts, and scores the saved state with the
pinned official evaluator. This layer only schedules; it never touches scoring.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WW = HERE.parents[2]                      # repository root
PIPELINE = HERE / "official_webarena.py"
PY = Path(os.environ.get("WEBWRIGHT_PYTHON") or WW / ".venv" / "bin" / "python")

# Outcomes that are real benchmark observations; anything else is an attempt worth retrying.
RESUMABLE = {"scored_correct", "scored_incorrect"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_trailing_json(text: str) -> dict:
    """Recover the pipeline's result object from stdout.

    Anchoring on the first `{` breaks as soon as anything earlier on stdout contains one: the
    parse fails, the result file is never written, and the task looks like it never ran. Scan
    candidate starts from the end instead and take the last one that parses.
    """
    for index in range(len(text) - 1, -1, -1):
        if text[index] != "{":
            continue
        try:
            value = json.loads(text[index:])
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {}


# Endpoints that refuse anonymous visitors, taken from the official
# browser_env/auto_login.py liveness check. A task's own start_url is the wrong probe: the
# shopping storefront and the reddit front page render fine without a session, so a dead
# cookie sails through and the failure only surfaces hours later as a wall of zeroes.
LOGIN_REQUIRED_PROBE = {
    "__GITLAB__": ("/-/profile", ""),
    "__SHOPPING__": ("/wishlist/", ""),
    "__SHOPPING_ADMIN__": ("/dashboard", "Dashboard"),
    "__REDDIT__": ("/user/MarvelsGrantMan136/account", "Delete"),
}


def probe_targets(state_path: Path, environments: dict) -> list[tuple[str, str]]:
    """Which login-walled endpoints this auth file is supposed to open.

    Combination files (gitlab.reddit_state.json) must satisfy every site they name, otherwise
    half a session passes as whole."""
    stem = state_path.name[: -len("_state.json")]
    out = []
    for site in stem.split("."):
        placeholder = f"__{site.upper()}__"
        spec = LOGIN_REQUIRED_PROBE.get(placeholder)
        urls = (environments.get(placeholder) or {}).get("urls") or []
        if spec and urls:
            out.append((str(urls[0]).rstrip("/") + spec[0], spec[1]))
    return out


def auth_is_live(state_path: Path, probe_url: str, keyword: str = "") -> bool:
    """A storage_state file can exist and still be dead — the site may have been reset or may
    still be starting. Existence checks miss that; the agent then fights a login wall and the
    run scores zero in a way that looks like incompetence. Probe before spending any tokens."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=str(state_path))
            page = context.new_page()
            page.goto(probe_url, wait_until="domcontentloaded", timeout=60000)
            body = page.content()
            landed = page.url.lower()
            if ("login[username]" in body or "please sign in" in body.lower()
                    or "/users/sign_in" in landed or "/customer/account/login" in landed):
                return False
            return keyword in body if keyword else True
        except Exception:
            return False
        finally:
            browser.close()


def renew_auth(state_path: Path, webarena_root: str) -> bool:
    """Re-run the official login for whichever sites this auth file covers.

    A session shared by hundreds of concurrent tasks does not last: the server can drop the
    logged-in user while the cookie itself stays valid and present, so nothing on the client
    side reveals it. Re-running the official auto_login is the only way back, and it has to be
    driven from here because a batch outlives any single check made before it started.
    """
    # auto_login pulls in the whole browser_env package (numpy, gymnasium), which the agent's
    # own environment need not carry. Point WEBARENA_LOGIN_PYTHON at an interpreter that has
    # the official requirements installed.
    interpreter = os.environ.get("WEBARENA_LOGIN_PYTHON") or sys.executable
    combination = state_path.name[: -len("_state.json")].split(".")
    script = (
        "from browser_env.auto_login import renew_comb;"
        f"renew_comb({sorted(combination)!r}, auth_folder={str(state_path.parent)!r})"
    )
    environment = dict(os.environ, PYTHONPATH=webarena_root)
    result = subprocess.run([interpreter, "-c", script], cwd=webarena_root,
                            env=environment, capture_output=True, text=True, timeout=600)
    return result.returncode == 0


def watch_auth(states, webarena_root, interval, stop):
    """Keep re-checking the sessions a batch depends on, and rebuild any that lapse."""
    while not stop.wait(interval):
        for state_path, targets in states.items():
            if all(auth_is_live(state_path, url, keyword) for url, keyword in targets):
                continue
            renewed = renew_auth(state_path, webarena_root)
            live = renewed and all(auth_is_live(state_path, url, keyword)
                                   for url, keyword in targets)
            print(json.dumps({"event": "auth_renewed", "state": str(state_path),
                              "ok": bool(live)}), flush=True)


def replay_and_score(run_dir: Path, task_id: int, args) -> dict:
    """Re-execute the frozen final_script.py in a clean workspace and score that.

    The inline score says whether the agent solved the task; this says whether the script it
    left behind still does. They come apart when the script depends on something only the
    original run had — an absolute path, a harness-private variable, a page already in the
    right state — and every one of those also makes the script useless as a reusable skill.
    Running both on every task turns that class of defect into something visible per task
    instead of something discovered by accident.
    """
    script = run_dir / "final_script.py"
    if not script.is_file():
        return {"status": "no_script"}
    workspace = run_dir / "replay"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    shutil.copy2(script, workspace / "final_script.py")
    started = time.time()
    try:
        proc = subprocess.run([str(PY), "final_script.py"], cwd=str(workspace),
                              env={**os.environ, "WORKSPACE_DIR": str(workspace)},
                              text=True, capture_output=True, timeout=args.replay_timeout)
        status = "completed" if proc.returncode == 0 else "process_error"
        returncode, tail = proc.returncode, (proc.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        status, returncode, tail = "timeout", None, ""
    state = workspace / "final_state.json"
    evaluation = None
    if state.is_file():
        command = [str(PY), str(HERE / "webarena_final_state_eval.py"),
                   "--task-id", str(task_id), "--final-state", str(state),
                   "--tasks", str(Path(args.webarena_root) / "config_files/test.raw.json"),
                   "--deployment-config", args.deployment_config,
                   "--webarena-root", args.webarena_root,
                   "--model-config", args.model_config,
                   "--output", str(workspace / "official_eval.json")]
        subprocess.run(command, cwd=str(WW), capture_output=True, text=True, timeout=600)
        if (workspace / "official_eval.json").is_file():
            evaluation = load(workspace / "official_eval.json")
    return {"status": status, "returncode": returncode, "stderr_tail": tail,
            "seconds": round(time.time() - started, 1),
            "produced_state": state.is_file(), "evaluation": evaluation}


def jobs_by_site(jobs):
    grouped = {}
    for job in jobs:
        grouped.setdefault(job[0], []).append(job)
    return grouped


def jobs_by_scope(jobs, scope_file):
    """Group by what a task writes to, so only tasks touching the same thing serialise.

    Mutating tasks cannot run beside anything that reads what they wrote, but two tasks in
    different GitLab projects or against different products never see each other. Grouping by
    site instead would serialise 127 GitLab tasks behind one another; grouping by write scope
    leaves 103 independent chains whose longest is 59.
    """
    scopes = load(scope_file)
    placement = {task_id: scope for scope, ids in scopes.items() for task_id in ids}
    grouped = {}
    for site, task_id in jobs:
        grouped.setdefault(placement.get(task_id, f"{site}:*"), []).append((site, task_id))
    return grouped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webarena-root", required=True)
    ap.add_argument("--deployment-config", required=True)
    ap.add_argument("--task-ids", required=True, help="JSON file holding a list of task ids")
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument("--workers", type=int, default=64,
                    help="global cap on how many tasks run at once. With --serial-groups each "
                         "chain is its own single-worker pool, so without this the 103 chains "
                         "would all start at once and overwhelm one deployment.")
    ap.add_argument("--per-site-workers", type=int, default=12)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--sites", default="")
    ap.add_argument("--limit-per-site", type=int, default=0)
    ap.add_argument("--task-id", type=int, action="append")
    ap.add_argument("--progress", default="")
    ap.add_argument("--serial-groups", default="",
                    help="serial_groups.json from partition_tasks.py; one chain per write "
                         "scope, chains running concurrently")
    ap.add_argument("--replay-eval", action="store_true",
                    help="also re-execute each frozen final_script.py and score that")
    ap.add_argument("--replay-timeout", type=int, default=600)
    ap.add_argument("--replay-only", action="store_true",
                    help="do not generate; replay the final_script.py each task already left "
                         "behind and score that. For mutating tasks this is the only honest "
                         "way to run the replay: inline replay re-applies the write on top of "
                         "the state the generation run just produced, so it has to happen "
                         "after the deployment is reset, as its own phase.")
    ap.add_argument("--replay-results-root", default="",
                    help="where --replay-only writes its scores; defaults to "
                         "<results-root>_replay so the generation scores stay intact")
    ap.add_argument("--auth-recheck-seconds", type=int, default=300,
                    help="how often to re-check and rebuild lapsed sessions; 0 disables")
    ap.add_argument("--skip-auth-probe", action="store_true",
                    help="skip the pre-flight storage_state liveness check")
    args = ap.parse_args()
    if args.replay_eval and args.replay_only:
        raise SystemExit("--replay-eval is the inline variant; --replay-only replaces it")
    if args.replay_eval and args.serial_groups:
        raise SystemExit("--replay-eval replays in the state the run just produced, which "
                         "re-applies the write. Serial (mutating) batches must instead be "
                         "reset and then replayed with --replay-only.")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing")

    tasks = {t["task_id"]: t for t in load(Path(args.webarena_root) / "config_files/test.raw.json")}
    wanted = load(args.task_ids)
    jobs = [(tasks[i]["sites"][0], i) for i in wanted if i in tasks]
    if args.task_id:
        keep_ids = set(args.task_id)
        jobs = [j for j in jobs if j[1] in keep_ids]
    if args.sites:
        keep = {s.strip() for s in args.sites.split(",") if s.strip()}
        jobs = [j for j in jobs if j[0] in keep]
    if args.limit_per_site:
        seen = {}
        capped = []
        for job in jobs:
            seen[job[0]] = seen.get(job[0], 0) + 1
            if seen[job[0]] <= args.limit_per_site:
                capped.append(job)
        jobs = capped

    if not args.skip_auth_probe:
        deployment = load(args.deployment_config)
        auth_root = deployment.get("auth_root")
        environments = deployment.get("environments") or {}
        checked, dead = {}, []
        for _site, task_id in jobs:
            raw = tasks[task_id].get("storage_state")
            if not raw or not auth_root:
                continue
            state = Path(auth_root) / Path(str(raw)).name
            if state in checked:
                continue
            if not state.is_file():
                dead.append(f"{state} (missing)")
                checked[state] = False
                continue
            targets = probe_targets(state, environments)
            if not targets:
                dead.append(f"{state} (no login-walled probe known for this file)")
                checked[state] = False
                continue
            failed = [url for url, keyword in targets if not auth_is_live(state, url, keyword)]
            checked[state] = not failed
            if failed:
                dead.append(f"{state} (session rejected at {', '.join(failed)})")
        for state, ok in checked.items():
            print(json.dumps({"event": "auth_probe", "state": str(state), "live": ok}), flush=True)
        probes = {state: probe_targets(state, environments) for state in checked}
        if dead:
            raise SystemExit("auth state not usable; regenerate with the official "
                             "browser_env/auto_login.py after the site is fully up:\n  "
                             + "\n  ".join(dead))

    active, active_lock = set(), threading.Lock()
    stopping = threading.Event()

    def stop_active(*_):
        with active_lock:
            stopping.set()
            pids = list(active)
        for pid in pids:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGINT, stop_active)
    signal.signal(signal.SIGTERM, stop_active)

    def run(job):
        site, task_id = job
        result = Path(args.results_root) / site / f"task{task_id}.json"
        if result.exists():
            try:
                if load(result).get("evaluation", {}).get("status") in RESUMABLE:
                    rec = load(result)
                    return {"site": site, "task_id": task_id, "status": "resumed",
                            "score": rec["evaluation"].get("score")}
            except (OSError, ValueError):
                pass
        if stopping.is_set():
            return {"site": site, "task_id": task_id, "status": "skipped_stopping"}
        out_dir = Path(args.output_root) / site
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [str(PY), str(PIPELINE), "pipeline", "--task-id", str(task_id),
               "--webarena-root", args.webarena_root,
               "--deployment-config", args.deployment_config,
               "--output-dir", str(out_dir),
               "--config", "base.yaml", "--config", args.model_config,
               "--model-config", args.model_config,
               "--timeout", str(args.timeout)]
        started = time.time()
        # Spawn and register under one lock. Registering after Popen returns leaves a window
        # in which a stop signal sees an empty set and the child survives as an orphan, still
        # driving a browser against the deployment. Checking the flag inside the lock closes
        # the other side of it: either this child is in the set before the stopper reads it,
        # or the stopper got there first and it is never spawned.
        with active_lock:
            if stopping.is_set():
                return {"site": site, "task_id": task_id, "status": "skipped_stopping"}
            proc = subprocess.Popen(cmd, cwd=str(WW), text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, env=os.environ.copy(),
                                    start_new_session=True)
            active.add(proc.pid)
        out, err = proc.communicate()
        with active_lock:
            active.discard(proc.pid)

        payload = parse_trailing_json(out)
        evaluation = payload.get("evaluation") or {}
        if payload and args.replay_eval:
            run_dir = (payload.get("run") or {}).get("run_dir")
            if run_dir:
                payload["replay"] = replay_and_score(Path(run_dir), task_id, args)
                inline = (payload.get("evaluation") or {}).get("score")
                replayed = ((payload["replay"].get("evaluation") or {}) or {}).get("score")
                payload["replay"]["matches_inline"] = (inline == replayed)
        if payload:
            payload["deployment"] = {
                "config": str(Path(args.deployment_config).resolve()),
                "sites": {k: (v.get("urls") or [None])[0]
                          for k, v in (load(args.deployment_config).get("environments") or {}).items()},
            }
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        return {"site": site, "task_id": task_id,
                "status": "ok" if proc.returncode == 0 else "process_error",
                "returncode": proc.returncode,
                "score": evaluation.get("score"),
                "eval_status": evaluation.get("status"),
                "eval_types": evaluation.get("eval_types"),
                "timed_out": (payload.get("run") or {}).get("timed_out"),
                "wall_seconds": round(time.time() - started, 1),
                "stderr": err.strip()[-400:]}

    replay_root = Path(args.replay_results_root or (str(args.results_root).rstrip("/") + "_replay"))

    def run_replay(job):
        """Replay one task's frozen script against the current (reset) deployment."""
        site, task_id = job
        started = time.time()
        source = Path(args.results_root) / site / f"task{task_id}.json"
        out = replay_root / site / f"task{task_id}.json"
        if not source.is_file():
            return {"site": site, "task_id": task_id, "status": "no_generation_result"}
        if stopping.is_set():
            return {"site": site, "task_id": task_id, "status": "skipped_stopping"}
        record = load(source)
        run_dir = (record.get("run") or {}).get("run_dir")
        if not run_dir:
            return {"site": site, "task_id": task_id, "status": "no_run_dir"}
        replay = replay_and_score(Path(run_dir), task_id, args)
        inline = (record.get("evaluation") or {}).get("score")
        replayed = ((replay.get("evaluation") or {}) or {}).get("score")
        replay["matches_inline"] = (inline == replayed)
        payload = {"task_id": task_id, "site": site, "run": record.get("run"),
                   "inline_evaluation": record.get("evaluation"), "replay": replay,
                   "deployment": record.get("deployment")}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"site": site, "task_id": task_id, "status": replay.get("status"),
                "inline_score": inline, "replay_score": replayed,
                "matches_inline": replay["matches_inline"],
                "wall_seconds": round(time.time() - started, 1)}

    print_lock = threading.Lock()
    progress_path = Path(args.progress) if args.progress else None
    done, total = [0], len(jobs)

    stop_watching = threading.Event()
    if not args.skip_auth_probe and args.auth_recheck_seconds > 0:
        threading.Thread(target=watch_auth,
                         args=(probes, args.webarena_root, args.auth_recheck_seconds,
                               stop_watching),
                         daemon=True).start()

    grouped = (jobs_by_scope(jobs, args.serial_groups) if args.serial_groups
               else jobs_by_site(jobs))

    worker = run_replay if args.replay_only else run

    gate = threading.Semaphore(max(1, args.workers))

    def run_one(job):
        with gate:
            row = worker(job)
        with print_lock:
            done[0] += 1
            row["done"], row["total"] = done[0], total
            line = json.dumps(row, ensure_ascii=False)
            print(line, flush=True)
            if progress_path:
                with progress_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        return row

    # One pool per site, each drawing from that site's shared queue. Within a site any free
    # worker takes the next task, so the run does not trail off into a single straggler while
    # the rest idle; across sites the pools simply run side by side. A single global pool with
    # per-site semaphores would instead let one busy site's queued tasks occupy every thread
    # and starve the others.
    per_group = 1 if args.serial_groups else args.per_site_workers
    sizes = {group: min(per_group, len(group_jobs))
             for group, group_jobs in grouped.items()}
    print(json.dumps({"event": "start", "tasks": total, "sites": sizes,
                      "concurrency": min(sum(sizes.values()), args.workers),
                      "global_cap": args.workers,
                      "mode": "replay-only" if args.replay_only else "generate",
                      "per_site_workers": args.per_site_workers}), flush=True)
    failures = 0
    pools = {site: concurrent.futures.ThreadPoolExecutor(max_workers=size)
             for site, size in sizes.items()}
    try:
        futures = [pools[site].submit(run_one, job)
                   for site, site_jobs in grouped.items() for job in site_jobs]
        for future in concurrent.futures.as_completed(futures):
            failures += future.result()["status"] == "process_error"
    finally:
        stop_watching.set()
        for pool in pools.values():
            pool.shutdown(wait=False)
    print(json.dumps({"event": "end", "process_errors": failures}), flush=True)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
