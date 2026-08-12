#!/usr/bin/env python3
"""Smoke-run a few WebArena mutate tasks through Webwright. No eval, no reset.

Purpose: observe how many times the agent actually executes the mutating action,
and whether it gets confused by its own side effects.
"""
import json
import os, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
WW = Path(os.environ.get("WA_WEBWRIGHT", Path(__file__).resolve().parents[3]))
PY = os.environ.get("WA_PYTHON", sys.executable)
MODEL_CFG = os.environ["WA_MODEL_CONFIG"]     # e.g. model_gateway_54.yaml
EVAL_CFG = str(WW / "evals/webarena/model.eval.yaml")
CONFIG = json.loads(Path(os.environ["WA_CONFIG"]).read_text())   # verified_config.json
RUNS = HERE / "mutate_smoke_runs"
TIMEOUT = int(os.environ.get("WA_TIMEOUT", "2400"))  # round 1: 1500s was short for 2/6

PLACEHOLDER = {
    "gitlab": "__GITLAB__", "shopping": "__SHOPPING__",
    "shopping_admin": "__SHOPPING_ADMIN__", "reddit": "__REDDIT__",
    "wikipedia": "__WIKIPEDIA__", "map": "__MAP__",
}

SPEC = """

## Required final output
When the task is complete, write $WORKSPACE_DIR/agent_response.json as:
{"task_type":"MUTATE","status":"SUCCESS|FAILURE","retrieved_data":null,
 "summary":"<one line on what you changed>"}
"""


def resolve(url_tpl, sites):
    url = url_tpl
    for site in sites:
        ph = PLACEHOLDER[site]
        url = url.replace(ph, CONFIG["environments"][ph]["urls"][0])
    for ph, env in CONFIG["environments"].items():
        url = url.replace(ph, env["urls"][0])
    return url


def creds(sites):
    env = CONFIG["environments"].get(PLACEHOLDER.get(sites[0], ""), {})
    return env.get("credentials") or {}


def complete_response(runs_root, key):
    """Stop the run the moment the agent declares a terminal result.

    Webwright keeps rewriting and re-running final_script.py after it has already
    produced an answer. On task 460 that turned one 15% price cut into seven
    (45.00 -> 14.42); run_1 had already written status=SUCCESS at the correct
    38.25. Mirrors has_complete_agent_response() in cross_task_eval.py.
    """
    for d in Path(runs_root).glob(f"{key}_*"):
        f = d / "agent_response.json"
        if not f.exists():
            continue
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (str(payload.get("task_type", "")).upper() == "MUTATE"
                and payload.get("status") in ("SUCCESS", "FAILURE")):
            return True
    return False


def run(item):
    key = f"task{item['task_id']}_{item['cat']}"
    url = resolve(item["start_urls"][0], item["sites"])
    c = creds(item["sites"])
    login = (f"\nIf login is required, use username `{c.get('username','')}` "
             f"and password `{c.get('password','')}`.") if c else ""
    prompt = f"Complete this web task.\n\nGoal: {item['intent']}\nStart URL: {url}{login}{SPEC}"

    RUNS.mkdir(parents=True, exist_ok=True)
    log = RUNS / f"{key}.log"
    cmd = [PY, "-m", "webwright.run.cli", "main",
           "-t", prompt, "--task-id", key, "--start-url", url, "-o", str(RUNS),
           "-c", "base.yaml", "-c", MODEL_CFG, "-c", EVAL_CFG]
    rec_dir = RUNS / "_rec" / key
    rec_dir.mkdir(parents=True, exist_ok=True)
    hosts = ",".join(sorted({
        u.split("//", 1)[-1].split("/", 1)[0]
        for e in CONFIG["environments"].values() for u in e.get("urls", [])
    }))
    env = dict(os.environ,
               PYTHONPATH=f"{HERE / 'warec'}:{WW / 'src'}",
               WA_REC_DIR=str(rec_dir),
               WA_REC_HOSTS=hosts)
    t0 = time.time()
    status = "ok"
    with log.open("w", encoding="utf-8") as f:
        f.write(f"=== {item['cat']} | task {item['task_id']} | tpl {item['tpl']}\n{item['intent']}\n\n")
        f.flush()
        p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT,
                             cwd=str(WW), env=env, start_new_session=True)
        deadline = time.time() + TIMEOUT
        while p.poll() is None:
            if time.time() > deadline:
                status = "timeout"
                os.killpg(os.getpgid(p.pid), 9)
                break
            if complete_response(RUNS, key):
                status = "stopped_after_response"
                os.killpg(os.getpgid(p.pid), 9)
                f.write("\nSTOPPED_AFTER_AGENT_RESPONSE\n")
                break
            time.sleep(5)
    return {"key": key, "task_id": item["task_id"], "cat": item["cat"],
            "status": status, "rc": p.returncode, "secs": round(time.time() - t0)}


if __name__ == "__main__":
    picks = sys.argv[1] if len(sys.argv) > 1 else "picked.json"
    items = json.loads((HERE / picks).read_text())
    RUNS = HERE / f"runs_{Path(picks).stem}"      # keep rounds in separate roots
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(run, items))
    (RUNS / "_summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    for r in results:
        print(f"{r['cat']:12s} task{r['task_id']:<4d} {r['status']:8s} rc={r['rc']} {r['secs']}s")
