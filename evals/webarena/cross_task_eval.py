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
import re
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
For catalog category/range tasks, a product whose displayed title directly states the requested
category or function is an in-scope record. Do not exclude it because of packaging, fit, wording,
or an imagined quality distinction that the goal did not request; exclude accessories and records
whose displayed title does not actually describe the requested product/function.
When a task names the current website/store as the venue of the user's purchases, that name scopes
the site's authenticated order history; it is not an additional per-order merchant filter unless
the acquired records expose merchant identity and the goal actually distinguishes merchants.
Preserve transaction semantics independently of acquisition. Unless the current goal explicitly
requests them, canceled/refunded orders are not completed spending or sales; do not aggregate them
merely because a primitive returned them. Likewise, "items sold" means summed site-reported
quantities, not the number of distinct line-item rows.

## Required final output
Write $WORKSPACE_DIR/agent_response.json as:
{"task_type":"RETRIEVE","status":"SUCCESS|NOT_FOUND_ERROR",
 "retrieved_data":<a JSON list or null>,"error_details":null}
"""

OFFICIAL_RETRIEVE_SPEC = ANSWER_SPEC + """

## Official WebArena answer and browser-state capture
The official evaluator consumes a textual answer and, for some tasks, the final URL. Immediately
before closing the same live browser page, also write `await page.content()` verbatim to
`$WORKSPACE_DIR/final_state.html` and write `$WORKSPACE_DIR/final_state.json` as:
{"final_url": page.url, "html_path": "final_state.html",
 "document_status": <the final document HTTP status integer or null>,
 "answer": <the concise textual answer to the goal>}
Keep `agent_response.json.retrieved_data` and `final_state.json.answer` semantically identical.
Do not invent the final URL or DOM and do not use a HAR as a substitute.
"""

NAVIGATE_SPEC = """

## Required final browser-state output
This is a NAVIGATE task. Complete the requested navigation in a real Playwright page. Immediately
before closing the browser, wait for the destination to settle and save the state from that same
live page:

1. Write `await page.content()` verbatim to `$WORKSPACE_DIR/final_state.html`.
2. Write `$WORKSPACE_DIR/final_state.json` as:
   {"final_url": page.url, "html_path": "final_state.html",
    "document_status": <the final document HTTP status integer or null>, "answer": ""}
3. Write `$WORKSPACE_DIR/agent_response.json` as:
   {"task_type":"NAVIGATE","status":"SUCCESS","retrieved_data":null,
    "error_details":null}

Do not invent the final URL or DOM and do not use a HAR as a substitute. The official WebArena
evaluator will score the saved URL and DOM. Only put a non-empty value in `answer` when the task
itself requires an explicit terminal answer such as `N/A`.
"""


def prepend_nonempty_hint(prompt, hint):
    """Keep a routed SKIP byte-identical to the scratch solve prompt."""
    return hint + "\n" + prompt if hint else prompt

VANILLA_FINAL_STATE_SPEC = """

## Final browser-state capture
Complete the objective using the real Playwright page. Immediately before closing the browser,
wait for the final page to settle, write `await page.content()` verbatim to
`$WORKSPACE_DIR/final_state.html`, and write `$WORKSPACE_DIR/final_state.json` as:
{"final_url": page.url, "html_path": "final_state.html",
 "document_status": <the final document HTTP status integer or null>, "answer": ""}
Do not invent the URL or DOM and do not use a HAR as a substitute. If the objective itself requires
an explicit terminal textual response, store it in `answer`; otherwise leave `answer` empty.
"""


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def is_official_webarena_task(task):
    return isinstance(task.get("eval"), dict)


def expected_task_type(task, default="retrieve"):
    if is_official_webarena_task(task):
        return str(default).lower()
    expected = next(
        (item.get("expected", {}) for item in task.get("eval", [])
         if item.get("evaluator") == "AgentResponseEvaluator"),
        {},
    )
    return str(expected.get("task_type", "retrieve")).lower()


def load_official_execution_task(metadata_task, tasks_path):
    """Load task text/config from WebArena while retaining Verified only as split metadata."""
    rows = load_json(tasks_path)
    task_id = metadata_task["task_id"]
    official = next((row for row in rows if row.get("task_id") == task_id), None)
    if official is None:
        raise ValueError(f"official WebArena task {task_id} is missing from {tasks_path}")
    for field in ("intent_template_id", "sites"):
        if official.get(field) != metadata_task.get(field):
            raise ValueError(
                f"official/Verified metadata mismatch for task {task_id}: {field} "
                f"{official.get(field)!r} != {metadata_task.get(field)!r}"
            )
    return official


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
        allowed_sites = split.get("sites") or [split["site"]]
        if len(task["sites"]) != 1 or task["sites"][0] not in allowed_sites:
            errors.append(f"task {tid} is not single-site in {allowed_sites}")
        desired_type = str(split.get("task_type", "retrieve")).lower()
        if is_official_webarena_task(task):
            eval_types = set(task.get("eval", {}).get("eval_types") or [])
            unsupported = eval_types - {"url_match", "program_html", "string_match"}
            if desired_type == "navigate" and (not eval_types or unsupported):
                errors.append(
                    f"official task {tid} has unsupported Navigate evaluators "
                    f"{sorted(eval_types)}"
                )
        else:
            names = {e["evaluator"] for e in task.get("eval", [])}
            if "AgentResponseEvaluator" not in names:
                errors.append(f"task {tid} has no AgentResponseEvaluator")
            if expected_task_type(task) != desired_type:
                errors.append(f"task {tid} is not {desired_type}")
    return errors


def validate_official_task_metadata(split, dataset, tasks_path):
    """Check that Verified grouping keys can safely index the official task source."""
    verified = {row["task_id"]: row for row in dataset}
    official = {row["task_id"]: row for row in load_json(tasks_path)}
    heldout_ids = [tid for group in split["heldout"] for tid in group["task_ids"]]
    errors = []
    for task_id in heldout_ids:
        if task_id not in official:
            errors.append(f"official WebArena task {task_id} is missing")
            continue
        if task_id not in verified:
            continue
        for field in ("intent_template_id", "sites"):
            if official[task_id].get(field) != verified[task_id].get(field):
                errors.append(f"official/Verified task {task_id} {field} mismatch")
    return errors


def resolve_url(task, config):
    urls = task.get("start_urls") or []
    url = task.get("start_url") or (urls[0] if urls else "")
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
            response = load_json(run_dir / "agent_response.json")
            answer = response.get("retrieved_data")
            if response.get("task_type") == "NAVIGATE" and (run_dir / "final_state.json").exists():
                answer = load_json(run_dir / "final_state.json").get("answer", "")
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
    arms = {"scratch", "workflow", "primitive"}
    if not runs.exists() or mode not in arms:
        return
    patterns = [pattern for opposite in arms - {mode} for pattern in (
        f"task*_{opposite}_*", f"task*_{opposite}.log", f"task*_{opposite}.json",
    )]
    exposed = []
    for pattern in patterns:
        exposed.extend(path for path in runs.glob(pattern) if path.exists())
    # Retrieval records are treatment artifacts even when their filename omits an arm suffix.
    if mode != "primitive":
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


def has_complete_final_state(runs, key):
    matches = sorted(glob.glob(str(Path(runs) / f"{key}_*")))
    if not matches:
        return False
    run_dir = Path(matches[-1])
    try:
        state = load_json(run_dir / "final_state.json")
    except (OSError, ValueError):
        return False
    if not isinstance(state, dict) or not str(state.get("final_url") or "").strip():
        return False
    if isinstance(state.get("html"), str):
        return True
    html_path = state.get("html_path")
    if not isinstance(html_path, str):
        return False
    resolved = (run_dir / html_path).resolve()
    try:
        resolved.relative_to(run_dir.resolve())
    except ValueError:
        return False
    return resolved.is_file()


def has_complete_agent_response(runs, key, task_type="retrieve"):
    """Completion is the artifact, not a non-null answer.

    NOT_FOUND_ERROR legitimately uses retrieved_data=null; treating null as unfinished makes those
    tasks run until timeout even after the benchmark response has been emitted.
    """
    matches = sorted(glob.glob(str(Path(runs) / f"{key}_*")))
    if not matches:
        return False
    path = Path(matches[-1]) / "agent_response.json"
    try:
        payload = load_json(path)
    except (OSError, ValueError):
        return False
    expected_type = str(task_type).upper()
    response_complete = (
        isinstance(payload, dict)
        and payload.get("task_type") == expected_type
        and payload.get("status") in (
            {"SUCCESS", "NOT_FOUND_ERROR"} if expected_type == "RETRIEVE" else {"SUCCESS"}
        )
        and "retrieved_data" in payload
    )
    if not response_complete or expected_type != "NAVIGATE":
        return response_complete
    return has_complete_final_state(runs, key)


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


def normalize_official_answer(run_dir):
    """Bridge structured agent output to WebArena's required textual STOP answer."""
    path = Path(run_dir) / "final_state.json"
    state = load_json(path)
    answer = state.get("answer", "")
    status = state.get("document_status")
    answer_needs_change = not isinstance(answer, str)
    status_needs_change = status is not None and not isinstance(status, int)
    if not answer_needs_change and not status_needs_change:
        return False
    backup = Path(run_dir) / "final_state.agent.json"
    if not backup.exists():
        backup.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    normalizations = []
    if answer_needs_change:
        if answer is None:
            rendered = "N/A"
        elif isinstance(answer, list):
            rendered = ", ".join(
                item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                for item in answer
            )
        else:
            rendered = json.dumps(answer, ensure_ascii=False)
        state["answer"] = rendered
        normalizations.append("structured_answer_to_official_text_v1")
    if status_needs_change:
        text_status = str(status).strip()
        state["document_status"] = int(text_status) if text_status.isdigit() else None
        normalizations.append("document_status_to_integer_or_null_v1")
    state["artifact_normalizations"] = normalizations
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def score_navigate(tid, run_dir, config, webarena_tasks, webarena_root, model_config=None):
    normalize_official_answer(run_dir)
    output = run_dir / "webarena_final_state_eval.json"
    command = [
        sys.executable, str(HERE / "webarena_final_state_eval.py"),
        "--task-id", str(tid),
        "--final-state", str(run_dir / "final_state.json"),
        "--tasks", str(webarena_tasks),
        "--deployment-config", str(config),
        "--webarena-root", str(webarena_root),
        "--output", str(output),
    ]
    if model_config:
        command += ["--model-config", str(model_config)]
    proc = subprocess.run(command, capture_output=True, text=True)
    try:
        result = load_json(output)
    except (OSError, ValueError):
        return None, {
            "module_path": None,
            "git_commit": None,
            "error": (proc.stderr or proc.stdout).strip()[-2000:],
        }
    return result.get("score"), {
        "module_path": str(Path(webarena_root) / "evaluation_harness" / "evaluators.py"),
        "git_commit": result.get("official_webarena_commit"),
        "eval_types": result.get("eval_types"),
        "adapter_result": str(output),
    }


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


def verify_direct_primitive_contract(task, proposal, selected, *, llm_fn=None):
    """Verify a proposed direct reuse plan against selected primitive contracts."""
    if llm_fn is None:
        from webwright.skill_factory.llm import llm_json as llm_fn
    contracts = [{key: primitive.get(key) for key in (
        "primitive_id", "capability", "owns", "does_not_own", "input_contract",
        "output_contract", "requires", "provides", "supported_patterns", "guarantees",
        "acceptance_checks", "source_evidence",
    )} for primitive in selected]
    return llm_fn(
        "Verify one proposed primitive reuse plan as a contract refinement of at least one "
        "closed website-acquisition sub-operation. Do not require the primitives to solve the "
        "whole task. Check exactly three obligations: (1) input_reachability: every selected "
        "primitive input needed by the proposal is available from the task or an earlier "
        "selected output, without leaving an internal site identifier/configuration gap; "
        "(2) guarantee_sufficiency: the primitive guarantees are strong enough for the claim "
        "made for the specific local acquisition it replaces, not necessarily for the final task. "
        "A page/search/detail acquisition may pass even when workflow code must repeat it, select "
        "candidates, paginate, filter, or format, provided the contract exposes usable records and "
        "a defensible continuation/stopping signal. Ranked/partial/query-scoped results still "
        "cannot close open-world entity discovery or prove exhaustive sets, global nearest/shortest, "
        "or absence. A scope-level multi-query primitive may nevertheless close the concrete local "
        "acquisition of executing, merging, and deduplicating every caller-supplied search; it does "
        "not thereby prove that the caller chose an exhaustive query family. When a task requires "
        "a non-default value or a combination of independently "
        "exposed site-configuration inputs, source examples are not sufficient: an explicit "
        "`guarantees` field must enumerate or validate the supported combination, otherwise "
        "guarantee_sufficiency MUST fail. Site configuration means transport profile, endpoint, "
        "base URL, port, backend, authentication/session mode, or another deployment control. "
        "Ordinary task inputs such as a product brand, search query, place name, filter value, "
        "page number, or page size are NOT site configuration and must not trigger this rule; "
        "(3) closed_acquisition: at least one concrete site acquisition is fully replaced, not "
        "merely assisted while that same local acquisition still has to run. Fetching and parsing "
        "one declared search page, filtered page, feed-metadata page, or detail page counts as a "
        "closed acquisition when its typed output is directly usable; do not reject it merely "
        "because other task acquisitions remain. Remaining task discovery, repetition, filtering, "
        "aggregation, semantic choice, and formatting are allowed. Be conservative only about the "
        "guarantee needed by the claimed local substitution. Return only JSON: "
        "{\"verdict\":\"accept|reject\","
        "\"checks\":{\"input_reachability\":\"pass|fail\","
        "\"guarantee_sufficiency\":\"pass|fail\","
        "\"closed_acquisition\":\"pass|fail\"},"
        "\"closed_acquisitions\":[\"...\"],\"reason\":\"...\"}. ACCEPT requires all "
        "three checks to pass and at least one specific closed acquisition.",
        json.dumps({"task": task, "proposal": proposal,
                    "selected_contracts": contracts}, ensure_ascii=False),
    )


def deterministic_direct_contract_guard(task, selected, *, site, exposure_risk=None):
    """Reject a few explicit pre-planning hazards without pretending to understand semantics.

    The LLM still proposes reuse. This guard only enforces facts present in the task wording and
    machine-readable contracts: partial collections cannot close exhaustive acquisition, line
    records are not quantities, and unresolved chains cannot be genuinely late-bound in the
    current one-shot prompt architecture.
    """
    text = str(task).lower()
    if (exposure_risk or {}).get("chained_open_world") is True:
        return "unresolved chained acquisition cannot be late-bound in a one-shot prompt"

    def schema_keys(value):
        keys = set()
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                keys.update(str(key).lower() for key in properties)
            for child in value.values():
                keys.update(schema_keys(child))
        elif isinstance(value, list):
            for child in value:
                keys.update(schema_keys(child))
        return keys

    collection_keys = {
        "results", "records", "orders", "reviews", "items", "places", "candidates",
        "rows", "commits", "issues", "products",
    }
    selected_collections = [
        primitive for primitive in selected
        if schema_keys(primitive.get("output_contract") or {}) & collection_keys
    ]
    if re.search(r"\b(items?|units?)\s+sold\b", text):
        outputs = set().union(*(
            schema_keys(primitive.get("output_contract") or {}) for primitive in selected
        )) if selected else set()
        if not outputs & {"quantity", "qty", "ordered_quantity", "order_quantity"}:
            return "items sold requires quantity facts; line-item cardinality is insufficient"

    exhaustive = bool(re.search(
        r"\b(all|total number|how many|most recent|nearest|closest|nearby|within|at most)\b",
        text,
    ))
    if exhaustive and selected_collections and not any(
        (primitive.get("guarantees") or {}).get("completeness") == "complete"
        for primitive in selected_collections
    ):
        return "task requires exhaustive candidate acquisition but selected collection is partial"

    # Geographic category discovery is especially sensitive to query family and search radius.
    # Even a multi-query helper only executes caller guesses; it does not make them exhaustive.
    if site == "map" and exhaustive and any(
        "/places/" in str(primitive.get("primitive_id") or "")
        for primitive in selected
    ):
        return "open-world map candidate discovery is partial and unsafe before planning"
    return None


def classify_direct_exposure_risk(task, candidates, proposed_ids, *, llm_fn=None):
    """Detect a semantic branch that downstream pre-planning code could anchor incorrectly."""
    if llm_fn is None:
        from webwright.skill_factory.llm import llm_json as llm_fn
    return llm_fn(
        "Classify exactly one structural property of a web task. Set chained_open_world=true "
        "only when BOTH are required: (1) choose or resolve an upstream entity that is not fully "
        "named by the user, such as selecting one venue/product from a brand/category or vicinity; "
        "and (2) use that chosen entity as the anchor/input for a distinct downstream acquisition, "
        "including a detail page, review feed, candidate search, nearest comparison, or route. "
        "Example true: choose a generic brush product, then fetch that product's reviews. "
        "Example true: choose a Hilton near an "
        "airport, then find the nearest supermarket from that hotel. Example false: find the "
        "nearest pharmacy from fully named CMU. Example false: route between two fully named "
        "places. Do not treat ordinary filtering and ranking within one candidate set as a chain. "
        "Return only JSON {\"chained_open_world\":true|false,"
        "\"upstream_entity\":\"...\","
        "\"downstream_operation\":\"...\",\"reason\":\"...\"}.",
        json.dumps({"task": task, "proposed_primitive_ids": proposed_ids,
                    "candidate_contracts": candidates}, ensure_ascii=False),
    )


def retrieve_direct_primitives(task, library, *, site, max_primitives=5, llm_fn=None):
    """Metadata-first primitive routing without a scratch-first plan."""
    from webwright.skill_factory.audited_primitive_retrieve import retrieve_audited_primitives
    if llm_fn is None:
        from webwright.skill_factory.llm import llm_json as llm_fn
    route_state = {}

    def decide(current_task, candidates):
        candidate_ids = [
            str(item.get("primitive_id")) for item in candidates if item.get("primitive_id")
        ]
        risk = classify_direct_exposure_risk(
            current_task, candidates, candidate_ids, llm_fn=llm_fn,
        ) or {}
        # A false negative exposes candidate-acquisition code before the semantic anchor is fixed,
        # which is the costly error. Confirm negative classifications once and use the safer
        # positive verdict on disagreement; the later typed-contract gate still limits exposure.
        if risk.get("chained_open_world") is False:
            confirmation = classify_direct_exposure_risk(
                current_task, candidates, candidate_ids, llm_fn=llm_fn,
            ) or {}
            route_state["exposure_risk_confirmation"] = confirmation
            if confirmation.get("chained_open_world") is True:
                risk = confirmation
        route_state["exposure_risk"] = risk
        proposal = llm_fn(
            "Route site primitives for DIRECT pre-planning injection using metadata only. "
            "An independent structural classifier result is supplied as exposure_risk. Treat a "
            "valid chained_open_world boolean as authoritative; do not reclassify it. "
            "Do not require or mention a scratch plan. USE only when selected primitives cover "
            "the complete website-specific acquisition needed by the task. ADAPT when a primitive "
            "provides a necessary, nontrivial acquisition or stable site-parsing sub-operation "
            "whose typed output is directly usable while the agent supplies remaining discovery, "
            "filtering, aggregation, ranking, semantic judgment, or formatting. SKIP when the "
            "primitive is merely related, needs unavailable inputs, supplies only a downstream "
            "operation without the task's core candidate set, duplicates work the agent must still "
            "perform, or would anchor the agent on an incomplete strategy. For open-ended "
            "category/vicinity/nearest/all tasks, candidate "
            "discovery is core: never ADAPT using only a single-query or single-page search primitive. "
            "When an available scope-level primitive executes multiple caller-supplied searches and "
            "merges/deduplicates their records, prefer it for candidate acquisition; the workflow still "
            "chooses query terms, semantic filters, and final ranking. If no such broader acquisition "
            "is selected, SKIP rather than anchor the agent on one query. Also SKIP chained open-world "
            "tasks when an ambiguous upstream entity choice (for example choosing one venue from a "
            "brand/category) determines a later search or nearest comparison, unless a selected "
            "primitive contract owns a sufficient upstream selection criterion. Merely combining a "
            "generic multi-search primitive with a downstream route/detail primitive does not close "
            "that semantic branch and is likely to anchor the wrong upstream entity. This restriction "
            "does not apply to a single-stage nearest/category task or to routes between fully named "
            "entities. When exposure_risk.chained_open_world is false, do not apply this chained-task "
            "restriction: evaluate ordinary local contract usefulness. When it is true, candidate "
            "selection will be handled by a separate late-bound gate, so propose every locally useful "
            "primitive and do not force SKIP solely because the task is chained. Never infer capabilities "
            "absent from metadata. Select at most five. Return JSON "
            "{\"decision\":\"use|adapt|skip\",\"primitive_ids\":[],\"reason\":\"...\","
            "\"remaining_gap\":[]}. No patches field is needed in direct mode.",
            json.dumps({"task": current_task, "exposure_risk": risk,
                        "candidates": candidates}, ensure_ascii=False),
        )
        proposed_ids = [str(x) for x in (proposal or {}).get("primitive_ids") or []]
        is_chained = risk.get("chained_open_world") is True
        if is_chained:
            # This runner has one prompt boundary. Exposing a supposedly "late-bound" route/detail
            # method here still changes planning before the upstream entity is selected. Until the
            # runtime has a real second injection phase, chained tasks must remain scratch.
            proposal = dict(proposal or {})
            proposal.update({
                "decision": "skip", "primitive_ids": [],
                "reason": "direct exposure risk gate: unresolved chained acquisition",
            })
        elif risk.get("chained_open_world") is not False and str(
            (proposal or {}).get("decision") or ""
        ).lower() in {"use", "adapt"}:
            # Malformed risk output is not permission to inject code before planning.  Falling
            # back to scratch preserves the control arm's capability and makes this gate fail-safe.
            proposal = dict(proposal or {})
            proposal.update({
                "decision": "skip", "primitive_ids": [],
                "reason": "direct exposure risk gate: malformed classification",
            })
        selected_by_id = {str(item.get("primitive_id")): item for item in candidates}
        proposed = [selected_by_id[pid] for pid in (proposal or {}).get("primitive_ids") or []
                    if pid in selected_by_id]
        guard_reason = deterministic_direct_contract_guard(
            current_task, proposed, site=site, exposure_risk=risk,
        )
        if guard_reason:
            proposal = dict(proposal or {})
            proposal.update({"decision": "skip", "primitive_ids": [],
                             "reason": "deterministic contract guard: " + guard_reason})
        return proposal

    def verify(current_task, proposal, selected):
        return verify_direct_primitive_contract(
            current_task, proposal, selected, llm_fn=llm_fn,
        )

    retrieval = retrieve_audited_primitives(
        task, library, site=site, max_primitives=max_primitives,
        decide_fn=decide, verify_fn=verify, scratch_plan=None,
    )
    # Direct injection is itself an intervention: even correct low-level code can anchor the
    # solver on the wrong upstream entity in a chained open-world task.  Keep that semantic
    # decision in scratch rather than exposing downstream primitives before planning.
    return retrieval


def prepare_workflow_hint(task, library, *, forced_skill_id=None):
    """Retrieve and fully inject a standalone workflow without primitive material."""
    root = Path(library).resolve()
    if forced_skill_id:
        source = root / forced_skill_id / "skill.py"
        meta_path = root / forced_skill_id / "meta.json"
        if not source.is_file() or not meta_path.is_file():
            return {"decision": "skip", "skill_id": None,
                    "reason": f"frozen workflow skill missing: {forced_skill_id}", "hint": ""}
        meta = load_json(meta_path)
        decision, reason = "use", "exact frozen TRAIN template workflow"
        skill_id = forced_skill_id
    else:
        from webwright.tools.skill_use import recommend
        rec = recommend(task["intent"], root)
        if rec.get("verdict") == "skip" or not rec.get("skill_id"):
            return {"decision": "skip", "skill_id": None,
                    "reason": rec.get("reason", "no useful workflow"), "hint": ""}
        skill_id = rec["skill_id"]
        source = root / skill_id / "skill.py"
        meta = load_json(root / skill_id / "meta.json")
        decision, reason = "adapt", rec.get("reason", "related cross-template workflow")
    code = source.read_text(encoding="utf-8")
    hint = (
        "## Frozen workflow material\n"
        f"Decision: {decision}; workflow: {skill_id}\n"
        f"Template: {meta.get('template', '')}\n"
        "This is a standalone workflow prior, not a site primitive. Read the complete source "
        "below, reuse only what fits the current task, and produce your own standalone final "
        "script. Do not assume its task-specific final selection is valid here.\n"
        "```python\n" + code + "\n```\n"
    )
    return {"decision": decision, "skill_id": skill_id, "reason": reason, "hint": hint}


def run_one(args, split, dataset, config):
    tasks = {x["task_id"]: x for x in dataset}
    metadata_task = tasks[args.task_id]
    heldout_ids = {tid for x in split["heldout"] for tid in x["task_ids"]}
    if args.task_id not in heldout_ids and not args.allow_any_task:
        raise SystemExit(f"task {args.task_id} is not in the frozen heldout split")
    declared_task_type = str(split.get("task_type", "retrieve")).lower()
    task_type = expected_task_type(metadata_task, default=declared_task_type)
    if is_official_webarena_task(metadata_task):
        task = metadata_task
        task_source = "official_webarena"
    elif args.webarena_tasks:
        task = load_official_execution_task(metadata_task, args.webarena_tasks)
        task_source = "official_webarena"
    else:
        task = metadata_task
        task_source = "webarena_verified"
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
    output_schema = (
        next(
            (item.get("results_schema") for item in metadata_task.get("eval", [])
             if item.get("evaluator") == "AgentResponseEvaluator"),
            None,
        )
        if task_type == "retrieve" and task_source != "official_webarena" else None
    )
    schema_note = (
        "\nRequired `retrieved_data` JSON schema: "
        + json.dumps(output_schema, ensure_ascii=False)
        if output_schema and task_type == "retrieve" else ""
    )
    if (task_type == "retrieve" and isinstance(output_schema, dict)
            and output_schema.get("type") == "null"):
        schema_note += (
            "\nA null-only result schema does not permit SUCCESS with null data. Continue "
            "acquisition until absence is justified; then return NOT_FOUND_ERROR with "
            "retrieved_data=null."
        )
    task_spec = (
        VANILLA_FINAL_STATE_SPEC if task_type == "navigate" and args.vanilla_task_interface
        else NAVIGATE_SPEC if task_type == "navigate"
        else OFFICIAL_RETRIEVE_SPEC if task_source == "official_webarena"
        else ANSWER_SPEC
    )
    prompt = (f"Complete this web task.\n\nGoal: {task['intent']}\n"
              f"Start URL: {url}{login}{schema_note}{task_spec}")
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
        retrieval = (retrieve_audited_primitives(
            task["intent"], args.candidate_library, site=site, max_primitives=5,
            scratch_plan=scratch_plan,
        ) if args.scratch_first else retrieve_direct_primitives(
            task["intent"], args.candidate_library, site=site, max_primitives=5,
        ))
        primitive_hint = render_audited_primitive_hint(
            retrieval, include_code=not args.primitive_metadata_only,
        )
        # SKIP with no selected primitive must be an exact no-op on the solve prompt.  Prefixing
        # even an empty hint with a newline makes the control prompt byte-different.
        prompt = prepend_nonempty_hint(prompt, primitive_hint)
        offered = retrieval.sources
        route_out = {
            "route_stage": "primitive", "route_decision": retrieval.decision,
            "reason": retrieval.reason, "remaining_gap": retrieval.remaining_gap,
        }
        write_audited_retrieval(
            Path(args.runs) / f"{key}.primitive_retrieval.json", retrieval,
            task=task["intent"],
        )
    elif mode == "workflow":
        configure_router_model(args.model_config)
        workflow = prepare_workflow_hint(
            task, Path(args.workflow_library) / site,
            forced_skill_id=args.workflow_skill_id,
        )
        prompt = workflow["hint"] + "\n" + prompt
        route_out = {
            "route_stage": "workflow", "route_decision": workflow["decision"],
            "reason": workflow["reason"], "remaining_gap": [],
            "skill_id": workflow["skill_id"],
        }
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
            if task_source == "official_webarena":
                complete_artifact = has_complete_final_state(Path(args.runs), key) and (
                    task_type == "navigate" and args.vanilla_task_interface
                    or has_complete_agent_response(Path(args.runs), key, task_type)
                )
            else:
                complete_artifact = has_complete_agent_response(
                    Path(args.runs), key, task_type
                )
            if complete_artifact:
                terminate_process_group(proc)
                f.write("\nSTOPPED_AFTER_FINAL_ARTIFACT\n")
                break
        if proc.poll() is None:
            timed_out = True
            terminate_process_group(proc)
            f.write("\nTIMEOUT\n")
    run_dir, answer, steps = collect_run(Path(args.runs), key)
    if (task_type == "navigate" and args.vanilla_task_interface and run_dir
            and has_complete_final_state(Path(args.runs), key)):
        response_path = run_dir / "agent_response.json"
        if not response_path.exists():
            response_path.write_text(json.dumps({
                "task_type": "NAVIGATE", "status": "SUCCESS",
                "retrieved_data": None, "error_details": None,
            }, indent=2) + "\n", encoding="utf-8")
        run_dir, answer, steps = collect_run(Path(args.runs), key)
    complete_response = has_complete_agent_response(Path(args.runs), key, task_type)
    # The official adapter evaluates the captured browser state even for retrieve tasks.
    # Treat a missing capture as an incomplete agent run instead of invoking the adapter and
    # crashing while normalizing a non-existent final_state.json.
    if task_source == "official_webarena" and run_dir:
        complete_response = complete_response and (run_dir / "final_state.json").exists()
    if task_source == "official_webarena":
        if not args.webarena_tasks or not args.webarena_root:
            raise SystemExit(
                "Official WebArena evaluation requires --webarena-tasks and --webarena-root"
            )
        if run_dir and complete_response:
            gold_score, eval_provenance = score_navigate(
                args.task_id, run_dir, args.config, args.webarena_tasks, args.webarena_root,
                args.model_config,
            )
        else:
            gold_score = None
            eval_provenance = {
                "module_path": str(Path(args.webarena_root) / "evaluation_harness" / "evaluators.py"),
                "git_commit": None,
            }
    else:
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
        "task_type": task_type,
        "task_source": task_source,
        "task_intent": task["intent"],
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
        "vanilla_task_interface": bool(args.vanilla_task_interface),
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
    parser.add_argument("mode", nargs="?", choices=["scratch", "workflow", "primitive", "routed", "oracle"])
    parser.add_argument("--split", default=str(HERE / "cross_task_split.json"))
    parser.add_argument("--dataset", default=os.environ.get("WEBARENA_DATASET", ""))
    parser.add_argument("--config", default=os.environ.get("WEBARENA_CONFIG", ""))
    parser.add_argument("--oracle-library", default=str(HERE / "oracle_library"))
    parser.add_argument(
        "--routed-library",
        default=str(HERE / "generated_oracle_library"),
        help="Frozen workflow + generated primitive library used by routed mode.",
    )
    parser.add_argument("--workflow-library", default=str(HERE / "workflow_library"))
    parser.add_argument("--workflow-skill-id",
                        help="T1 only: inject the exact frozen same-template workflow skill.")
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
    parser.add_argument(
        "--webarena-tasks",
        default=os.environ.get("WEBARENA_ORIGINAL_TASKS", ""),
        help="Original WebArena test config JSON used to score Navigate final state.",
    )
    parser.add_argument(
        "--webarena-root",
        default=os.environ.get("WEBARENA_ROOT", ""),
        help="Pinned official WebArena checkout containing evaluation_harness/evaluators.py.",
    )
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
    parser.add_argument(
        "--vanilla-task-interface", action="store_true",
        help="Navigate ablation: do not expose task type or response schema to the agent; "
             "the harness creates the evaluator response after final-state capture.",
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
        if str(split.get("task_type", "retrieve")).lower() == "navigate":
            if not args.webarena_tasks:
                errors.append("Navigate validation requires --webarena-tasks")
            else:
                errors.extend(validate_official_task_metadata(
                    split, dataset, args.webarena_tasks,
                ))
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
