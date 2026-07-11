#!/usr/bin/env python3
"""Reproduce the WebArena numbers in src/webwright/skills/README.md.

The headline table (held-out: 70% vs 55% accuracy, 14.7 vs 17.1 steps; train:
26/30 vs 23/30) comes from 100 solves over 10 task templates x 3 sites. This
script re-runs that experiment against YOUR WebArena deployment:

  train   30 tasks solved from scratch, scored against gold
  update  gold-admitted train solves -> one library skill per template
  heldout 20 unseen tasks, each solved twice: WITH the library and from scratch
  (optional) trainwith: the 30 train tasks re-solved WITH the library

Prerequisites (see README.md next to this file):
  - webwright installed (this repo, `pip install -e .` in a venv)
  - a WebArena deployment + microsoft/webarena-verified checked out:
      * its dataset json (tasks + gold answers)
      * your verified_config.json (maps site placeholders -> YOUR urls/credentials)
      * a python env with the `webarena_verified` package (for gold scoring)
  - env: OPENAI_API_KEY (and on a custom gateway OPENAI_ENDPOINT / OPENAI_MODEL,
    used by the skills module); the agent's model is set via the -c yaml stack.

Usage (one task at a time; each solve takes minutes — parallelize per template):
  python reproduce.py plan                          # print every command to run
  python reproduce.py train 279                     # solve one train task
  python reproduce.py update 279                    # build the template's skill
  python reproduce.py heldout 1 with|base           # one held-out solve
  python reproduce.py table [--results DIR]         # aggregate -> the README table

`table --results results.json` prints the table from the checked-in snapshot of the
run behind the README numbers (no network needed).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 10 retrieve-type templates across 3 domains (shopping_admin / gitlab / map), all with
# non-null golds in webarena-verified. Key = representative task_id; value = (train, held-out).
SPLITS = {
    # shopping_admin
    279: ([0, 3, 4],       [1, 2]),      # top-n best-selling entity in period
    198: ([198, 199, 203], [201, 202]),  # attribute of the {status} order
    11:  ([11, 14, 15],    [12, 13]),    # total number of reviews
    213: ([213, 214, 215], [216, 217]),  # title+rating of all 3-star reviews
    # gitlab
    132: ([132, 133, 136], [134, 135]),  # commits by {user} to {repo} on {date}
    303: ([303, 304, 307], [305, 306]),  # commits by {user} during {period}
    293: ([293, 294, 295], [296, 297]),  # SSH clone URL of {repo}
    # map
    151: ([151, 152, 153], [154, 155]),  # min car travel time between two places
    16:  ([16, 17, 18],    [19, 20]),    # walking+driving time for a route
    248: ([248, 249, 250], [251, 252]),  # coordinates of {location}
}

SITE_PLACEHOLDER = {"shopping": "__SHOPPING__", "shopping_admin": "__SHOPPING_ADMIN__",
                    "reddit": "__REDDIT__", "gitlab": "__GITLAB__"}

ANSWER_SPEC = (
    "\n\n## Required final output\n"
    "Additionally, write the final answer into $WORKSPACE_DIR/agent_response.json with the "
    'structure:\n{ "task_type": "RETRIEVE", "status": "SUCCESS|NOT_FOUND_ERROR", '
    '"retrieved_data": <list or null>, "error_details": null }\n'
    "retrieved_data is a list; if nothing matches, use NOT_FOUND_ERROR and null."
)


# ---------------------------------------------------------------- dataset / config
class Bench:
    def __init__(self, dataset: Path, config: Path):
        self.data = {t["task_id"]: t for t in json.loads(Path(dataset).read_text())}
        self.conf = json.loads(Path(config).read_text())

    def task(self, tid):
        return self.data[tid]

    def resolve(self, url):
        """Site placeholder -> the deployment url from YOUR verified_config.json."""
        for ph, ec in self.conf["environments"].items():
            urls = ec.get("urls", [])
            if urls and url == ph:
                return urls[0]
            if urls and url.startswith(ph + "/"):
                return urls[0].rstrip("/") + url[len(ph):]
        return url

    def credentials(self, site):
        ph = SITE_PLACEHOLDER.get(site)
        return self.conf["environments"].get(ph, {}).get("credentials")

    def prompt(self, tid):
        t = self.task(tid)
        url = self.resolve(t["start_urls"][0]) if t["start_urls"] else ""
        c = self.credentials(t["sites"][0])
        login = (f"\nIf login is required, use username `{c['username']}` "
                 f"password `{c['password']}`." if c else "")
        return (f"Complete the following web task.\n\n## Task\nGoal: {t['intent']}\n\n"
                f"Start URL: {url}{login}{ANSWER_SPEC}"), url


# ---------------------------------------------------------------- solve + collect
def collect(out_dir: Path, key: str) -> dict:
    dirs = sorted(glob.glob(str(out_dir / f"{key}_*")))
    d = Path(dirs[-1]) if dirs else None
    answer, steps, verdict = None, 0, None
    if d:
        arp = d / "agent_response.json"
        if arp.exists():
            try:
                answer = json.loads(arp.read_text()).get("retrieved_data")
            except Exception:
                pass
        traj = d / "trajectory.json"
        if traj.exists():
            try:
                steps = int((json.loads(traj.read_text()).get("info") or {}).get("api_calls") or 0)
            except Exception:
                pass
        sd = d / "skill_decision.json"
        if sd.exists():
            try:
                verdict = json.loads(sd.read_text()).get("verdict")
            except Exception:
                pass
    return {"answer": answer, "steps": steps, "verdict": verdict, "dir": str(d) if d else None}


def solve(args, bench: Bench, tid: int, key: str, with_skills: bool) -> dict:
    prompt, url = bench.prompt(tid)
    if with_skills:
        from webwright.skills import with_skill_hint
        prompt = with_skill_hint(prompt, task=bench.task(tid)["intent"],
                                 library=str(Path(args.out) / "library"))
    runs = Path(args.out) / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "webwright.run.cli", "main", "-t", prompt,
           "--task-id", key, "--start-url", url, "-o", str(runs),
           "-c", "base.yaml", "-c", args.model_config, "-c", str(HERE / "model.eval.yaml")]
    for attempt in range(1, 3):   # webwright occasionally stalls on step 1 — retry once
        log = runs / f"{key}.log"
        with log.open("a") as lf:
            try:
                subprocess.run(cmd, env=os.environ.copy(), stdout=lf,
                               stderr=subprocess.STDOUT, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                lf.write("\nTIMEOUT\n")
        res = collect(runs, key)
        if res["answer"] is not None or res["steps"] > 0:
            return res
        print(f"  [retry] attempt {attempt} hung (no answer, no steps)")
    return res


# ---------------------------------------------------------------- gold scoring
GOLD_EVAL = r'''
import json, sys
from pathlib import Path
from webarena_verified.api import WebArenaVerified
tid = int(sys.argv[1]); vd = Path(sys.argv[2]); cfg = Path(sys.argv[3])
har = vd / "network.har"   # AgentResponseEvaluator ignores the trace; the API requires one
har.write_text(json.dumps({"log": {"version": "1.2", "creator": {"name": "d", "version": "1"},
  "entries": [{"request": {"method": "GET", "url": "http://dummy.local", "headers": [],
  "queryString": [], "cookies": [], "bodySize": 0}, "response": {"status": 200,
  "statusText": "OK", "headers": [], "cookies": [], "content": {"size": 0,
  "mimeType": "text/plain"}, "bodySize": 0}, "cache": {}, "timings":
  {"send": 0, "wait": 0, "receive": 0}}]}}))
try:
    wa = WebArenaVerified(config=cfg)
    r = wa.evaluate_task(task_id=tid, agent_response=vd / "agent_response.json", network_trace=har)
    ag = [e for e in r.evaluators_results if e.evaluator_name == "AgentResponseEvaluator"]
    print(json.dumps({"ag": ag[0].score if ag else r.score}))
except Exception as e:
    print(json.dumps({"ag": None, "err": str(e)[:200]}))
'''


def gold_eval(args, tid: int, run_dir: str):
    p = subprocess.run([args.eval_python, "-c", GOLD_EVAL, str(tid), run_dir, args.config],
                       capture_output=True, text=True)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1]).get("ag")
    except Exception:
        return None


# ---------------------------------------------------------------- per-task records
def rec_path(args, key):
    return Path(args.out) / "results" / f"{key}.json"


def run_task(args, bench, tid, key, with_skills):
    p = rec_path(args, key)
    if p.exists() and json.loads(p.read_text()).get("answer") is not None:
        print(f"[resume] {key} already done")
        return
    res = solve(args, bench, tid, key, with_skills)
    score = gold_eval(args, tid, res["dir"]) if res["dir"] else None
    rec = {"tid": tid, "with_skills": with_skills, "answer": res["answer"],
           "steps": res["steps"], "correct": score == 1.0, "score": score,
           "params": bench.task(tid).get("instantiation_dict", {}), "verdict": res["verdict"],
           "dir": res["dir"]}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    print(f"[{key}] answer={json.dumps(res['answer'], ensure_ascii=False)[:80]} "
          f"steps={res['steps']} correct={rec['correct']} verdict={res['verdict']}")


def template_of(tid):
    for tmpl, (tr, te) in SPLITS.items():
        if tid in tr or tid in te:
            return tmpl
    raise SystemExit(f"task {tid} is not in SPLITS")


# ---------------------------------------------------------------- update (build skills)
def do_update(args, bench, tmpl):
    """Gold-admitted train solves of this template -> manifest -> skills update CLI."""
    tr, _ = SPLITS[tmpl]
    tmpl_str = bench.task(tr[0]).get("intent_template", "")
    runs = []
    for tid in tr:
        p = rec_path(args, f"t{tmpl}_train{tid}")
        if not p.exists():
            continue
        r = json.loads(p.read_text())
        if not r.get("correct") or not r.get("dir"):
            continue
        runs.append({"dir": r["dir"], "admit": True, "params": r.get("params", {}),
                     "verdict": "skip", "site": bench.task(tid)["sites"][0],
                     "output_schema": bench.task(tid)["eval"][0].get("results_schema")})
    print(f"template {tmpl}: {len(runs)} gold-admitted train solve(s)")
    if not runs:
        print("nothing admitted — run the train tasks first")
        return
    mf = Path(args.out) / f"manifest_t{tmpl}.json"
    mf.write_text(json.dumps({"template": tmpl_str, "runs": runs}, indent=2, ensure_ascii=False))
    lib = Path(args.out) / "library"
    p = subprocess.run([sys.executable, "-m", "webwright.skills.update",
                        "--manifest", str(mf), "--library", str(lib)],
                       env=os.environ.copy(), capture_output=True, text=True)
    print(p.stdout.strip() or p.stderr[-600:])


# ---------------------------------------------------------------- aggregate table
def table(results_path: Path):
    results_path = Path(results_path)
    if results_path.is_file():
        recs = json.loads(results_path.read_text())
    else:
        recs = {p.stem: json.loads(p.read_text()) for p in sorted(results_path.glob("*.json"))}
    if not recs:
        raise SystemExit(f"no per-task results at {results_path}")

    def agg(sel):
        rs = [v for k, v in recs.items() if sel(k)]
        if not rs:
            return None
        n = len(rs)
        ok = sum(1 for r in rs if r["correct"])
        return {"n": n, "correct": ok, "acc": 100.0 * ok / n,
                "steps": sum(r["steps"] for r in rs) / n}

    rows = [
        ("held-out  WITH library", agg(lambda k: "heldout" in k and k.endswith("_with"))),
        ("held-out  from scratch", agg(lambda k: "heldout" in k and k.endswith("_base"))),
        ("train     WITH library", agg(lambda k: "trainwith" in k)),
        ("train     from scratch", agg(lambda k: "_train" in k and "trainwith" not in k)),
    ]
    print(f"{'':24}  {'tasks':>5}  {'correct':>7}  {'accuracy':>8}  {'avg steps':>9}")
    for name, a in rows:
        if a is None:
            print(f"{name:24}  (no runs yet)")
        else:
            print(f"{name:24}  {a['n']:>5}  {a['correct']:>7}  {a['acc']:>7.1f}%  {a['steps']:>9.1f}")
    return rows


# ---------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["plan", "train", "trainwith", "update", "heldout", "table"])
    ap.add_argument("arg", nargs="?", help="task_id (train/heldout) or template id (update)")
    ap.add_argument("mode", nargs="?", default="with", choices=["with", "base"],
                    help="heldout only: solve WITH the library or from scratch")
    ap.add_argument("--dataset", default=os.environ.get("WEBARENA_DATASET", ""),
                    help="webarena-verified dataset json (or env WEBARENA_DATASET)")
    ap.add_argument("--config", default=os.environ.get("WEBARENA_CONFIG", ""),
                    help="your verified_config.json with YOUR deployment urls (or env WEBARENA_CONFIG)")
    ap.add_argument("--eval-python", default=sys.executable,
                    help="python that has the webarena_verified package (gold scoring)")
    ap.add_argument("--model-config", default="model_openai.yaml",
                    help="model modifier yaml for the agent (stacked on base.yaml)")
    ap.add_argument("--out", default="runs_eval", help="working dir for runs/results/library")
    ap.add_argument("--results", default="", help="table only: aggregate this dir or merged .json instead of --out")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args(argv)

    if args.cmd == "table":
        table(Path(args.results) if args.results else Path(args.out) / "results")
        return 0
    if args.cmd == "plan":
        print("# run these (each solve takes minutes; parallelize per template):")
        for tmpl, (tr, te) in SPLITS.items():
            for t in tr:
                print(f"python reproduce.py train {t}")
            print(f"python reproduce.py update {tmpl}")
            for t in te:
                print(f"python reproduce.py heldout {t} with")
                print(f"python reproduce.py heldout {t} base")
            # trainwith is optional — it feeds only the "train (seen tasks)" table
            for t in tr:
                print(f"python reproduce.py trainwith {t}")
        print("python reproduce.py table")
        return 0

    if not args.dataset or not args.config:
        raise SystemExit("need --dataset and --config (or WEBARENA_DATASET / WEBARENA_CONFIG env) — "
                         "see README.md for how to get both from microsoft/webarena-verified")
    bench = Bench(Path(args.dataset), Path(args.config))
    tid = int(args.arg)
    if args.cmd == "train":
        run_task(args, bench, tid, f"t{template_of(tid)}_train{tid}", False)
    elif args.cmd == "trainwith":
        run_task(args, bench, tid, f"t{template_of(tid)}_trainwith{tid}", True)
    elif args.cmd == "update":
        do_update(args, bench, tid)
    elif args.cmd == "heldout":
        run_task(args, bench, tid, f"t{template_of(tid)}_heldout{tid}_{args.mode}",
                 args.mode == "with")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
