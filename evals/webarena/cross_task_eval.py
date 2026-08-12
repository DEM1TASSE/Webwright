#!/usr/bin/env python3
"""Strict same-site, cross-template WebArena primitive experiment.

Examples:
  python cross_task_eval.py validate
  python cross_task_eval.py run 52 scratch ...
  python cross_task_eval.py run 52 routed ...
  python cross_task_eval.py table
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
NULL_EXPECTED_FIX = "c7449d8c68542b7fabec5ac89a985d7051023384"
ANSWER_SPEC = """

## Abstraction boundary
Site primitives provide objective website facts and stable site-specific parsing only. Treat their
typed output as evidence, not as the task's semantic decision. Derive subjective categories,
relevance judgments, filters, comparisons, and aggregation from the current goal itself. Do not
broaden a requested category merely because a record is generally negative or loosely related.
Before using supplied material, state which part of the task its output contract covers and which
capabilities remain uncovered. Relevant but partial material is evidence, not a complete plan; do
not spend effort adapting it when it does not materially advance the missing capability.
Only when the task requires a subjective classification: optimize precision, state a short
inclusion and exclusion rule, make record-level decisions with rationales, and verify that the
executed included set matches the semantic plan. Do not replace those decisions with an approximate
broad keyword list.

## Required final output
Write $WORKSPACE_DIR/agent_response.json as:
{"task_type":"RETRIEVE","status":"SUCCESS|NOT_FOUND_ERROR",
 "retrieved_data":<a JSON list or null>,"error_details":null}
"""


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_split(split, dataset):
    tasks = {x["task_id"]: x for x in dataset}
    source_templates = set(split["source"]["intent_template_ids"])
    heldout_templates = {x["intent_template_id"] for x in split["heldout"]}
    heldout_ids = [tid for x in split["heldout"] for tid in x["task_ids"]]
    errors = []
    if source_templates & heldout_templates:
        errors.append("source and heldout intent_template_id sets overlap")
    gate = split.get("gate") or {}
    if len(heldout_ids) < gate.get("minimum_instances", 1):
        errors.append("too few heldout instances")
    if len(heldout_templates) < gate.get("minimum_heldout_templates", 1):
        errors.append("too few heldout templates")
    for tid in heldout_ids:
        task = tasks.get(tid)
        if task is None:
            errors.append(f"missing dataset task {tid}")
            continue
        declared = next(x["intent_template_id"] for x in split["heldout"]
                        if tid in x["task_ids"])
        if task["intent_template_id"] != declared:
            errors.append(f"task {tid} template mismatch")
        if task["sites"] != [split["site"]]:
            errors.append(f"task {tid} is not single-site {split['site']}")
        names = {e["evaluator"] for e in task.get("eval", [])}
        if names != {"AgentResponseEvaluator"}:
            errors.append(f"task {tid} evaluator set is {sorted(names)}")
        expected = task["eval"][0].get("expected", {})
        if str(expected.get("task_type", "")).lower() != "retrieve":
            errors.append(f"task {tid} is not retrieve")
    return errors


def resolve_url(task, config):
    url = task.get("start_urls", [""])[0]
    for placeholder, env in config["environments"].items():
        urls = env.get("urls") or []
        if urls and (url == placeholder or url.startswith(placeholder + "/")):
            return urls[0].rstrip("/") + url[len(placeholder):]
    return url


def credentials_for(task, config):
    placeholders = {
        "gitlab": "__GITLAB__",
        "shopping": "__SHOPPING__",
        "shopping_admin": "__SHOPPING_ADMIN__",
        "reddit": "__REDDIT__",
    }
    env = config["environments"].get(placeholders.get(task["sites"][0], ""), {})
    return env.get("credentials")


def collect_run(runs, key):
    matches = sorted(glob.glob(str(runs / f"{key}_*")))
    run_dir = Path(matches[-1]) if matches else None
    answer, steps = None, 0
    if run_dir:
        try:
            answer = load_json(run_dir / "agent_response.json").get("retrieved_data")
        except (OSError, ValueError):
            pass
        try:
            steps = int((load_json(run_dir / "trajectory.json").get("info") or {})
                        .get("api_calls") or 0)
        except (OSError, ValueError):
            pass
    return run_dir, answer, steps


def assert_arm_isolation(runs: Path, mode: str) -> None:
    """Fail before execution when the run root exposes artifacts from the opposite arm."""
    if not runs.exists() or mode not in {"scratch", "primitive"}:
        return
    opposite = "primitive" if mode == "scratch" else "scratch"
    patterns = [
        f"task*_{opposite}_*",
        f"task*_{opposite}.log",
        f"task*_{opposite}.json",
    ]
    exposed = []
    for pattern in patterns:
        exposed.extend(path for path in runs.glob(pattern) if path.exists())
    # Retrieval records are treatment artifacts even when their filename omits an arm suffix.
    if mode == "scratch":
        exposed.extend(runs.glob("*.primitive_retrieval.json"))
    if exposed:
        sample = ", ".join(sorted(path.name for path in exposed)[:5])
        raise ValueError(
            f"strict arm isolation failed for {mode}: opposite-arm artifacts visible in "
            f"{runs}: {sample}"
        )


def read_primitive_execution_trace(run_dir: Path) -> list[dict]:
    """Read best-effort JSONL lifecycle events emitted by a vendored primitive consumer."""
    path = run_dir / "primitive_execution_trace.jsonl"
    if not path.exists():
        return []
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        event = str(value.get("event") or "")
        primitive_id = str(value.get("primitive_id") or "")
        if event not in {
            "entered", "completed", "acceptance_passed", "acceptance_failed", "fallback_used",
        } or not primitive_id:
            continue
        events.append({
            "primitive_id": primitive_id,
            "scratch_step_id": str(value.get("scratch_step_id") or ""),
            "event": event,
            "line": line_number,
        })
    return events


def complete_agent_response_path(runs, key):
    """Completion is the artifact, not a non-null answer.

    NOT_FOUND_ERROR legitimately uses retrieved_data=null; treating null as unfinished makes those
    tasks run until timeout even after the benchmark response has been emitted.
    """
    matches = sorted(glob.glob(str(Path(runs) / f"{key}_*")))
    if not matches:
        return None
    run_dir = Path(matches[-1])
    paths = [run_dir / "agent_response.json"]
    nested = []
    for candidate in (run_dir / "final_runs").glob("run_*/agent_response.json"):
        try:
            run_id = int(candidate.parent.name.removeprefix("run_"))
        except ValueError:
            continue
        nested.append((run_id, candidate))
    paths.extend(path for _, path in sorted(nested, reverse=True))
    for path in paths:
        try:
            payload = load_json(path)
        except (OSError, ValueError):
            continue
        if (isinstance(payload, dict)
                and payload.get("task_type") == "RETRIEVE"
                and payload.get("status") in {"SUCCESS", "NOT_FOUND_ERROR"}
                and "retrieved_data" in payload):
            return path
    return None


def has_complete_agent_response(runs, key):
    return complete_agent_response_path(runs, key) is not None


def promote_nested_agent_response(runs, key):
    """Copy a valid final-run response to the workspace location required by the benchmark."""
    path = complete_agent_response_path(runs, key)
    if path is None:
        return None
    matches = sorted(glob.glob(str(Path(runs) / f"{key}_*")))
    target = Path(matches[-1]) / "agent_response.json"
    if path != target:
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def terminate_process_group(proc, grace_seconds=20):
    """Stop a spawned agent and all of its descendants."""
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def classify_result(complete_response, gold_score, timed_out, process_returncode):
    if complete_response:
        if gold_score is None:
            return None, "evaluator_infrastructure_error"
        return gold_score == 1.0, (
            "scored_correct" if gold_score == 1.0 else "scored_incorrect"
        )
    if not timed_out and process_returncode not in (0, None):
        return None, "agent_process_infrastructure_error"
    return False, "agent_timeout_or_incomplete"


GOLD_EVAL = r"""
import json, sys
from pathlib import Path
from webarena_verified.api import WebArenaVerified
tid, run_dir, config = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
har = run_dir / "agent_response_only.har"
har.write_text(json.dumps({"log":{"version":"1.2","creator":{"name":"cross-task","version":"1"},
"entries":[{"request":{"method":"GET","url":"http://dummy.local","headers":[],"queryString":[],
"cookies":[],"bodySize":0},"response":{"status":200,"statusText":"OK","headers":[],"cookies":[],
"content":{"size":0,"mimeType":"text/plain"},"bodySize":0},"cache":{},
"timings":{"send":0,"wait":0,"receive":0}}]}}))
r = WebArenaVerified(config=config).evaluate_task(
    task_id=tid, agent_response=run_dir/"agent_response.json", network_trace=har)
scores = [x.score for x in r.evaluators_results if x.evaluator_name=="AgentResponseEvaluator"]
print(json.dumps({"score": scores[0] if scores else None}))
"""


def score(eval_python, tid, run_dir, config):
    proc = subprocess.run(
        [eval_python, "-c", GOLD_EVAL, str(tid), str(run_dir), str(config)],
        capture_output=True, text=True,
    )
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])["score"]
    except (IndexError, KeyError, ValueError):
        return None


def evaluator_provenance(eval_python):
    probe = subprocess.run(
        [
            eval_python,
            "-c",
            "import inspect,json,webarena_verified;"
            "print(json.dumps({'module_path':inspect.getfile(webarena_verified)}))",
        ],
        capture_output=True,
        text=True,
    )
    try:
        module_path = Path(json.loads(probe.stdout.strip().splitlines()[-1])["module_path"])
    except (IndexError, KeyError, ValueError):
        return {"module_path": None, "git_commit": None, "null_expected_fix": None}
    repo = next((p for p in module_path.parents if (p / ".git").exists()), None)
    commit = None
    has_fix = None
    if repo:
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        )
        commit = rev.stdout.strip() or None
        if commit:
            check = subprocess.run(
                ["git", "merge-base", "--is-ancestor", NULL_EXPECTED_FIX, commit],
                cwd=repo,
                capture_output=True,
            )
            has_fix = check.returncode == 0
    return {
        "module_path": str(module_path),
        "git_commit": commit,
        "null_expected_fix": has_fix,
    }


def prepare_routed_hint(task, library, *, primitive_record_path=None, route_fn=None):
    """Run the primitive-only cross-template router without launching the browser agent.

    Related workflows are not adaptation priors: every non-exact task passes through primitive
    metadata selection and then either receives full method code or runs from scratch.
    """
    if route_fn is None:
        from webwright.skill_factory.route import route as route_fn
    from webwright.tools.skill_use import recommend

    def cross_template_recommend(intent, root):
        rec = recommend(intent, root)
        if rec.get("verdict") == "run":
            rec = dict(rec)
            rec["verdict"] = "adapt"
            rec["reason"] = "cross-template evaluation never executes a workflow directly"
        return rec

    return route_fn(
        task["intent"],
        library,
        recommend_fn=cross_template_recommend,
        primitive_site=task["sites"][0],
        primitive_record_path=primitive_record_path,
        cross_template_workflow_first=False,
    )


def configure_router_model(model_config):
    """Use the same explicit backend config for routing and the downstream agent."""
    from webwright.skill_factory.llm import configure_llm

    config = yaml.safe_load(Path(model_config).read_text(encoding="utf-8")) or {}
    model = config.get("model")
    if not isinstance(model, dict):
        raise ValueError(f"{model_config}: missing model configuration")
    configure_llm(model)


def run_one(args, split, dataset, config):
    tasks = {x["task_id"]: x for x in dataset}
    task = tasks[args.task_id]
    heldout_ids = {tid for x in split["heldout"] for tid in x["task_ids"]}
    if args.task_id not in heldout_ids and not args.allow_any_task:
        raise SystemExit(f"task {args.task_id} is not in the frozen heldout split")
    site = task["sites"][0]
    mode = args.mode
    key = f"task{args.task_id}_{mode}"
    result_path = Path(args.results) / f"{key}.json"
    if args.strict_arm_isolation:
        assert_arm_isolation(Path(args.runs), mode)
    if result_path.exists() and not args.force:
        print(f"[resume] {result_path}")
        return

    url = resolve_url(task, config)
    credentials = credentials_for(task, config)
    login = ""
    if credentials:
        login = (f"\nIf login is required, use username `{credentials.get('username', '')}` "
                 f"and password `{credentials.get('password', '')}`.")
    output_schema = next(
        (item.get("results_schema") for item in task.get("eval", [])
         if item.get("evaluator") == "AgentResponseEvaluator"),
        None,
    )
    schema_note = (
        "\nRequired `retrieved_data` JSON schema: "
        + json.dumps(output_schema, ensure_ascii=False)
        if output_schema else ""
    )
    prompt = (f"Complete this web task.\n\nGoal: {task['intent']}\n"
              f"Start URL: {url}{login}{schema_note}{ANSWER_SPEC}\n"
              "This WebArena run is scored by an external evaluator. Do not run the optional "
              "webwright self_reflection tool and do not wait for self_reflect_result.json. "
              "After final_script.py has run successfully and the required workspace-level "
              "agent_response.json exists, declare done.")
    development_hint = ""
    if args.development_hint_file:
        if not args.allow_any_task:
            raise ValueError("--development-hint-file requires --allow-any-task")
        development_hint = Path(args.development_hint_file).read_text(encoding="utf-8").strip()
        prompt = ("## Development capability probe (not a primitive and not an answer)\n"
                  + development_hint
                  + "\nUse this only as a site-acquisition hypothesis. Verify it against the website, "
                    "generate the complete standalone solution yourself, and do not assume any "
                    "task answer from this hint.\n\n" + prompt)
    offered = []
    route_out = None
    scratch_plan = None
    if args.scratch_first:
        configure_router_model(args.model_config)
        from webwright.skill_factory.audited_primitive_retrieve import (
            draft_scratch_plan, render_frozen_scratch_plan,
        )
        plan_path = Path(args.runs) / f"task{args.task_id}.scratch_plan.json"
        if plan_path.exists():
            scratch_plan = load_json(plan_path)
            if scratch_plan.get("task") != task["intent"]:
                raise ValueError(f"scratch plan task mismatch: {plan_path}")
        else:
            scratch_plan = draft_scratch_plan(task["intent"], site=site)
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(json.dumps(scratch_plan, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        if mode == "scratch":
            prompt = render_frozen_scratch_plan(scratch_plan) + prompt
    if mode == "oracle":
        from webwright.skill_factory.primitive_retrieve import (
            render_primitive_hint, retrieve_primitives, write_retrieval_record,
        )
        retrieval = retrieve_primitives(
            task["intent"],
            args.oracle_library,
            site=site,
            max_primitives=5,
            rank_fn=(
                (lambda _task, _primitives: args.oracle_primitive_id)
                if args.oracle_primitive_id else None
            ),
        )
        prompt = render_primitive_hint(retrieval) + "\n" + prompt
        offered = retrieval.sources
        write_retrieval_record(
            Path(args.runs) / f"{key}.primitive_retrieval.json",
            retrieval,
            task=task["intent"],
        )
    elif mode == "primitive":
        configure_router_model(args.model_config)
        from webwright.skill_factory.audited_primitive_retrieve import (
            render_audited_primitive_hint,
            retrieve_audited_primitives,
            write_audited_retrieval,
        )
        retrieval = retrieve_audited_primitives(
            task["intent"], args.candidate_library, site=site, max_primitives=5,
            scratch_plan=scratch_plan,
        )
        prompt = render_audited_primitive_hint(
            retrieval, include_code=not args.primitive_metadata_only,
        ) + "\n" + prompt
        offered = retrieval.sources
        route_out = {
            "route_stage": "primitive", "route_decision": retrieval.decision,
            "reason": retrieval.reason, "remaining_gap": retrieval.remaining_gap,
        }
        write_audited_retrieval(
            Path(args.runs) / f"{key}.primitive_retrieval.json", retrieval,
            task=task["intent"],
        )
    elif mode == "routed":
        configure_router_model(args.model_config)
        route_out = prepare_routed_hint(
            task,
            args.routed_library,
            primitive_record_path=Path(args.runs) / f"{key}.primitive_retrieval.json",
        )
        prompt = (route_out.get("hint") or "") + "\n" + prompt
        offered = route_out.get("primitive_sources") or []

    Path(args.runs).mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "webwright.run.cli", "main",
        "-t", prompt, "--task-id", key, "--start-url", url, "-o", args.runs,
        "-c", "base.yaml", "-c", args.model_config, "-c", str(HERE / "model.eval.yaml"),
    ]
    log = Path(args.runs) / f"{key}.log"
    timed_out = False
    with log.open("a", encoding="utf-8") as f:
        proc = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + args.timeout
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(5)
            # The agent can continue reflecting after it has emitted a complete benchmark
            # artifact. Stop there: AgentResponseEvaluator needs no later browser events.
            if has_complete_agent_response(Path(args.runs), key):
                terminate_process_group(proc)
                f.write("\nSTOPPED_AFTER_AGENT_RESPONSE\n")
                break
        if proc.poll() is None:
            timed_out = True
            terminate_process_group(proc)
            f.write("\nTIMEOUT\n")
    promote_nested_agent_response(Path(args.runs), key)
    run_dir, answer, steps = collect_run(Path(args.runs), key)
    complete_response = has_complete_agent_response(Path(args.runs), key)
    eval_provenance = evaluator_provenance(args.eval_python)
    if eval_provenance["null_expected_fix"] is False:
        raise SystemExit(
            f"evaluator commit {eval_provenance['git_commit']} predates required "
            f"null expected-data fix {NULL_EXPECTED_FIX}"
        )
    gold_score = (
        score(args.eval_python, args.task_id, run_dir, args.config)
        if run_dir and complete_response else None
    )
    correct, run_status = classify_result(
        complete_response, gold_score, timed_out, proc.returncode
    )
    used = []
    declared = []
    declared_coverage = None
    if run_dir and (run_dir / "final_script.py").exists():
        from webwright.skill_factory.primitive_retrieve import (
            extract_primitive_usage, read_declared_coverage, read_declared_usage,
        )
        used = extract_primitive_usage((run_dir / "final_script.py").read_text(encoding="utf-8"))
        declared = read_declared_usage(run_dir / "primitive_usage.json")
        declared_coverage = read_declared_coverage(run_dir / "primitive_usage.json")
    execution_trace = read_primitive_execution_trace(run_dir) if run_dir else []
    record = {
        "task_id": args.task_id,
        "intent_template_id": task["intent_template_id"],
        "site": site,
        "mode": mode,
        "answer": answer,
        "steps": steps,
        "score": gold_score,
        "correct": correct,
        "run_status": run_status,
        "timed_out": timed_out,
        "process_returncode": proc.returncode,
        "evaluator": eval_provenance,
        "retrieved_primitives": offered,
        "route_stage": route_out.get("route_stage") if route_out else None,
        "route_decision": route_out.get("route_decision") if route_out else None,
        "route_reason": route_out.get("reason") if route_out else None,
        "route_remaining_gap": route_out.get("remaining_gap") if route_out else [],
        "routed_workflow_id": route_out.get("skill_id") if route_out else None,
        "declared_used_primitives": declared,
        "declared_primitive_coverage": declared_coverage,
        "code_incorporated_primitives": used,
        "primitive_execution_trace": execution_trace,
        "development_hint_file": args.development_hint_file or None,
        "primitive_metadata_only": bool(args.primitive_metadata_only),
        "run_dir": str(run_dir) if run_dir else None,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False))


def summarize(split, results_dir, routed_library):
    records = {p.stem: load_json(p) for p in Path(results_dir).glob("task*_*.json")}
    heldout_ids = [tid for x in split["heldout"] for tid in x["task_ids"]]
    comparison_mode = next((mode for mode in ("primitive", "routed", "oracle")
                            if any(key.endswith(f"_{mode}") for key in records)), "oracle")
    pairs, wins, losses = [], [], []
    for tid in heldout_ids:
        base = records.get(f"task{tid}_scratch")
        treatment = records.get(f"task{tid}_{comparison_mode}")
        if not base or not treatment:
            continue
        pair = {
            "task_id": tid,
            "template": treatment["intent_template_id"],
            "site": treatment["site"],
            "scratch": base["correct"],
            comparison_mode: treatment["correct"],
            "route_decision": treatment.get("route_decision"),
        }
        pairs.append(pair)
        if treatment["correct"] and not base["correct"]:
            wins.append(pair)
        if base["correct"] and not treatment["correct"]:
            losses.append(pair)
    win_templates = {x["template"] for x in wins}
    gate = split.get("gate") or {}
    complete = len(pairs) == len(heldout_ids)
    go = (complete and len(wins) - len(losses) >= gate.get("go_if_win_minus_loss_at_least", 1)
          and len(win_templates) >= gate.get("minimum_templates_with_wins", 1))
    treatment_runs = [x for x in records.values() if x.get("mode") == comparison_mode]
    if comparison_mode == "primitive":
        from webwright.skill_factory.audited_primitive_retrieve import load_candidate_index
        catalog_size = len(load_candidate_index(routed_library, split["site"])["primitives"])
    else:
        from webwright.skill_factory.primitive_catalog import PrimitiveCatalog
        catalog_size = len(PrimitiveCatalog(routed_library, split["site"]).list())
    by_template = {}
    for pair in pairs:
        row = by_template.setdefault(str(pair["template"]), {"pairs": 0, "wins": 0, "losses": 0})
        row["pairs"] += 1
        row["wins"] += int(pair in wins)
        row["losses"] += int(pair in losses)
    by_site = {}
    for pair in pairs:
        row = by_site.setdefault(
            pair["site"], {"pairs": 0, "scratch_correct": 0,
                           f"{comparison_mode}_correct": 0, "wins": 0, "losses": 0}
        )
        row["pairs"] += 1
        row["scratch_correct"] += int(pair["scratch"])
        row[f"{comparison_mode}_correct"] += int(pair[comparison_mode])
        row["wins"] += int(pair in wins)
        row["losses"] += int(pair in losses)
    decisions = {}
    for item in treatment_runs:
        decision = item.get("route_decision") or "unrecorded"
        decisions[decision] = decisions.get(decision, 0) + 1
    return {"complete": complete, "comparison_mode": comparison_mode,
            "pairs": len(pairs), "wins": len(wins),
            "losses": len(losses), "win_minus_loss": len(wins) - len(losses),
            "templates_with_wins": len(win_templates), "go": go,
            "scratch_correct": sum(bool(records.get(f"task{x}_scratch", {}).get("correct"))
                                   for x in heldout_ids),
            f"{comparison_mode}_correct": sum(
                bool(records.get(f"task{x}_{comparison_mode}", {}).get("correct"))
                for x in heldout_ids
            ),
            "code_incorporation_runs": sum(
                bool(x.get("code_incorporated_primitives")) for x in treatment_runs
            ),
            "declared_usage_runs": sum(
                bool(x.get("declared_used_primitives")) for x in treatment_runs
            ),
            "route_decisions": decisions,
            "by_site": by_site,
            "by_template": by_template,
            "catalog_growth": {
                "initial_active": catalog_size,
                "final_active": catalog_size,
                "promoted_after_pilot": 0,
                "reason": "Phase 0 GO gate failed; automatic catalog growth stopped.",
            }}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "plan", "run", "table"])
    parser.add_argument("task_id", nargs="?", type=int)
    parser.add_argument("mode", nargs="?", choices=["scratch", "primitive", "routed", "oracle"])
    parser.add_argument("--split", default=str(HERE / "cross_task_split.json"))
    parser.add_argument("--dataset", default=os.environ.get("WEBARENA_DATASET", ""))
    parser.add_argument("--config", default=os.environ.get("WEBARENA_CONFIG", ""))
    parser.add_argument("--oracle-library", default=str(HERE / "oracle_library"))
    parser.add_argument(
        "--routed-library",
        default=str(HERE / "generated_oracle_library"),
        help="Frozen workflow + generated primitive library used by routed mode.",
    )
    parser.add_argument(
        "--candidate-library",
        default=str(HERE / "audited_site_library_v2"),
        help="Audited candidate site packages used only by primitive mode.",
    )
    parser.add_argument(
        "--oracle-primitive-id",
        action="append",
        default=[],
        help="Force an exact generated primitive selection for oracle attribution; repeatable.",
    )
    parser.add_argument("--runs", default=str(HERE / ".runs"))
    parser.add_argument("--results", default=str(HERE / "cross_task_results"))
    parser.add_argument("--model-config", default="model_openai.yaml")
    parser.add_argument("--eval-python", default=sys.executable)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--strict-arm-isolation", action="store_true",
        help="Reject a run root containing artifacts from the opposite experimental arm.",
    )
    parser.add_argument(
        "--development-hint-file",
        help="Development probes only: prepend a non-code capability hypothesis. Requires "
             "--allow-any-task and is recorded in the result.",
    )
    parser.add_argument(
        "--scratch-first", action="store_true",
        help="Pilot only: freeze one task-only scratch plan for both arms and permit primitives "
             "only as contract-checked local step patches.",
    )
    parser.add_argument(
        "--primitive-metadata-only", action="store_true",
        help="Development ablation only: route normally but withhold selected primitive code.",
    )
    parser.add_argument("--allow-any-task", action="store_true",
                        help="Development probes only: permit a task outside the frozen split.")
    args = parser.parse_args(argv)
    if args.primitive_metadata_only and not args.allow_any_task:
        raise SystemExit("--primitive-metadata-only requires --allow-any-task")
    split = load_json(args.split)
    if args.command == "table":
        library = args.candidate_library if any(
            Path(args.results).glob("task*_primitive.json")
        ) else args.routed_library
        summary = summarize(split, args.results, library)
        summary_path = Path(args.results) / "summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    if not args.dataset:
        raise SystemExit("--dataset or WEBARENA_DATASET is required")
    dataset = load_json(args.dataset)
    if args.command == "validate":
        errors = validate_split(split, dataset)
        print("valid" if not errors else "\n".join(errors))
        return bool(errors)
    if args.command == "plan":
        for group in split["heldout"]:
            for tid in group["task_ids"]:
                print(f"python {Path(__file__).name} run {tid} scratch")
                print(f"python {Path(__file__).name} run {tid} routed")
        return 0
    if not args.config or args.task_id is None or args.mode is None:
        raise SystemExit("run requires task_id, mode, and --config/WEBARENA_CONFIG")
    run_one(args, split, dataset, load_json(args.config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
