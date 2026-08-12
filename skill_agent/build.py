"""Driver: stage each episode, launch the agent, verify and commit what came back.

The agent owns the procedure inside an episode. This module owns only what an agent must not
be trusted with: what goes into a workspace, whether the result actually verifies, and the
purely mechanical write to the library.

    PYTHONPATH=src:. python -m skill_agent.build \
        --workflows skill_agent/inputs/workflows \
        --output runs/agentic_v1 \
        --model-config /path/to/model_gateway.yaml

Two episode levels, matching where the pipeline's own context boundary falls:

    batch  — extract every workflow, then build primitives that survive the judge. Sees this
             batch's source code (~10k tokens at the current batch size) and the pool so far.
    site   — one episode over the accumulated pool. With a single batch it only assigns
             feature classes; with several it also repairs what batching broke.

Resumable: an already-committed batch and an already-rendered site are skipped on re-run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from webwright.skill_factory.audited_primitive_build import (
    apply_build_operations,
    partition_workflows,
    render_site_package,
    retrieve_pool,
    validate_build_proposal,
    validate_consolidation,
    write_candidate_review,
)
from webwright.skill_factory.site_package_candidate import expected_class_name

from . import context as ctx
from . import verify as verify_mod
from .portability import fstring_quote_reuse, make_portable
from .runner import AgentRunner, WebwrightRunner, env_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# A verify call spawns a whole judge episode inside one bash command; the per-command timeout
# has to cover that.
COMMAND_TIMEOUT_SECONDS = 1800
EPISODE = {
    "batch": {"step_limit": 80, "max_output_tokens": 16000},
    "site": {"step_limit": 50, "max_output_tokens": 16000},
}


def _prompt(name: str, **substitutions: object) -> str:
    text = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    for key, value in substitutions.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def _fresh_workspace(root: Path, *parts: str) -> Path:
    workspace = root.joinpath(*parts)
    if workspace.exists():
        shutil.rmtree(workspace)
    (workspace / "in").mkdir(parents=True, exist_ok=True)
    (workspace / "out").mkdir(parents=True, exist_ok=True)
    return workspace


def _stage_rules(workspace: Path, names: list[str], *, site: str) -> None:
    """Rules are files the agent reads at the step they govern, not prompt bulk it carries."""
    rules = workspace / "in" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    for name in names:
        text = (PROMPT_DIR / "rules" / f"{name}.md").read_text(encoding="utf-8")
        (rules / f"{name}.md").write_text(text.replace("{{SITE}}", site), encoding="utf-8")


def _stage_sources(workspace: Path, workflows: list[dict]) -> None:
    sources = workspace / "in" / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    for workflow in workflows:
        (sources / f"{workflow['id']}.py").write_text(workflow["code"], encoding="utf-8")


def _stage_method_code(workspace: Path, primitives: list[dict]) -> None:
    code = workspace / "in" / "code"
    code.mkdir(parents=True, exist_ok=True)
    for primitive in primitives:
        if primitive.get("method") and primitive.get("method_code"):
            (code / f"{primitive['method']}.py").write_text(primitive["method_code"], encoding="utf-8")


def _feedback(workspace: Path, errors: list[str]) -> None:
    ctx.dump(workspace / "in" / "previous_attempt_feedback.json", {
        "retry_instruction": "A previous attempt at this episode was rejected. Correct every "
                             "error below without inventing code or evidence.",
        "validation_feedback": errors,
    })


def _episode_env(library: Path, number: int, model_config: str) -> None:
    """The driver verifies with the same state resolution the agent's commands used."""
    os.environ[ctx.ENV_LIBRARY] = str(library)
    os.environ[ctx.ENV_BATCH] = str(number)
    os.environ[ctx.ENV_MODEL_CONFIG] = str(model_config)
    os.environ[ctx.ENV_REPO_ROOT] = str(REPO_ROOT)


def commit_batch(library: Path, number: int, workspace: Path, context: dict,
                 proposal: dict, verdicts: dict) -> list[dict]:
    """Mechanical: no judgement here, which is why it is the driver's job and not the agent's."""
    batch = context.get("batch") or []
    extractions = ctx.load_extractions(workspace, batch=batch)
    pool = ctx.load_pool(library)
    accepted, errors = validate_build_proposal(
        proposal, site=context["site"], batch=batch, pool=pool,
        all_workflows={str(k): v for k, v in (context.get("all_workflows") or {}).items()},
        extractions=extractions)
    if errors:  # verify already passed; a mismatch here is a bug, not an agent mistake
        raise ValueError(f"commit re-validation disagreed with verify: {errors}")

    for workflow, extraction in zip(batch, extractions):
        directory = library / "extractions" / str(workflow["id"])
        ctx.dump(directory / "extraction.json", extraction)
        ctx.dump(directory / "validation.json", {"accepted": True, "errors": []})

    pool, diff = apply_build_operations(pool, accepted)
    directory = library / "batches" / f"batch_{number:03d}"
    ctx.dump(directory / "input.json", {
        "site": context["site"], "batch": batch, "extractions": extractions,
        "catalog_index": context.get("catalog_index") or [],
        "retrieved_primitives": context.get("retrieved_primitives") or []})
    ctx.dump(directory / "proposal.json", proposal)
    ctx.dump(directory / "validation.json", {"accepted": True, "errors": []})
    ctx.dump(directory / "quality_verdicts.json", verdicts)
    ctx.dump(directory / "workflow_attribution.json", proposal.get("workflow_attribution") or [])
    ctx.dump(directory / "primitive_diff.json", diff)
    ctx.dump(directory / "snapshot" / "primitive_pool.json", list(pool.values()))
    for primitive in pool.values():
        (directory / "snapshot" / "code").mkdir(parents=True, exist_ok=True)
        (directory / "snapshot" / "code" / f"{primitive['method']}.py").write_text(
            primitive["method_code"], encoding="utf-8")
    ctx.save_pool(pool, library)
    return diff


def render_final(library: Path, site: str, context: dict, proposal: dict) -> dict:
    pool = ctx.load_pool(library)
    final, errors, coverage = validate_consolidation(
        proposal, site=site, pool=pool,
        workflows={str(k): v for k, v in (context.get("workflows") or {}).items()})
    if errors:
        raise ValueError(f"render re-validation disagreed with verify: {errors}")

    # render_site_package round-trips through ast.unparse, which normalizes string literals to
    # single quotes and can turn portable f"{p['lon']}" into 3.12-only f'{p['lon']}'. No agent
    # can prevent that, so repair it here — and only if the rewrite parses to the same AST.
    code, notes = make_portable(render_site_package(site, final))
    if fstring_quote_reuse(code):
        raise ValueError(f"{site} rendered package is not parsable before Python 3.12 and could "
                         f"not be repaired: {fstring_quote_reuse(code)}")
    for note in notes:
        print(f"  [render] {note}")

    ctx.dump(library / "pre_consolidation" / "primitive_pool.json", list(pool.values()))
    ctx.dump(library / "consolidation" / "proposal.json", proposal)
    ctx.dump(library / "consolidation" / "validation.json", {"accepted": True, "errors": []})
    ctx.dump(library / "consolidation" / "coverage.json", coverage)
    final_dir = library / "final_candidate"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "package.py").write_text(code, encoding="utf-8")
    ctx.dump(final_dir / "index.json", {
        "schema_version": 1, "status": "candidate", "approved": False, "site": site,
        "root_class": expected_class_name(site), "primitives": final,
        "package_sha256": "sha256:" + hashlib.sha256(code.encode()).hexdigest()})
    ctx.dump(final_dir / "primitive_pool.json", final)
    write_candidate_review(final_dir, site=site, primitives=final)
    ctx.dump(library / "audit.json", {
        "site": site, "status": "candidate",
        "consolidation_operations": proposal.get("operations") or [], "coverage": coverage})
    return {"final_count": len(final), "pre_consolidation_count": len(pool)}


def _run_episode(runner: AgentRunner, *, level: str, task: str, workspace: Path,
                 commit) -> list[str]:
    """One attempt: run the agent, verify what it left behind, commit only if it verifies."""
    episode = runner.run_episode(stage=level, task=task, workspace=workspace, **EPISODE[level])
    errors = [f"episode failed: {episode.error}"] if episode.error else []
    if not errors:
        code, _, verify_errors, extra = verify_mod.run(workspace)
        errors = list(verify_errors)
        if code == 0:
            commit(extra)
    return errors, episode.api_calls


def run_batch(runner: AgentRunner, *, site: str, batch: list[dict], number: int,
              all_workflows: dict, library: Path, runs: Path, max_attempts: int) -> None:
    if (library / "batches" / f"batch_{number:03d}" / "validation.json").exists():
        print(f"  [batch {number}] cached")
        return

    pool = ctx.load_pool(library)
    context = {
        "mode": "batch", "site": site, "batch": batch, "pool": list(pool.values()),
        "catalog_index": [{key: value.get(key) for key in (
            "primitive_id", "method", "capability", "input_contract", "output_contract",
            "supported_patterns")} for value in pool.values()],
        "retrieved_primitives": retrieve_pool(batch, pool),
        "all_workflows": all_workflows,
    }
    errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        workspace = _fresh_workspace(runs, f"batch_{number:03d}", f"attempt_{attempt}")
        ctx.dump(workspace / "in" / "context.json", context)
        _stage_sources(workspace, batch)
        _stage_method_code(workspace, list(pool.values()))
        _stage_rules(workspace, ["extract", "build"], site=site)
        if errors:
            _feedback(workspace, errors)
        errors, calls = _run_episode(
            runner, level="batch", workspace=workspace,
            task=_prompt("procedure_batch", SITE=site, BATCH=number, BATCH_SIZE=len(batch),
                         WORKFLOW_IDS=", ".join(str(x["id"]) for x in batch)),
            commit=lambda extra: commit_batch(library, number, workspace, context,
                                              extra["proposal"], extra.get("verdicts") or {}))
        print(f"  [batch {number}] attempt {attempt}: "
              f"{'committed' if not errors else f'{len(errors)} error(s)'} ({calls} model calls)")
        if not errors:
            return
    raise ValueError(f"{site} batch {number} failed after {max_attempts} attempt(s): {errors}")


def run_site(runner: AgentRunner, *, site: str, all_workflows: dict, library: Path,
             runs: Path, max_attempts: int, batch_count: int = 1) -> None:
    if (library / "final_candidate" / "index.json").exists():
        print("  [site] cached")
        return

    pool = ctx.load_pool(library)
    context = {"mode": "site", "site": site, "workflows": all_workflows}
    single_batch = batch_count <= 1
    rules_doc = "classify" if single_batch else "consolidate"
    procedure = "procedure_classify" if single_batch else "procedure_consolidate"
    errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        workspace = _fresh_workspace(runs, "site", f"attempt_{attempt}")
        ctx.dump(workspace / "in" / "context.json", context)
        _stage_sources(workspace, list(all_workflows.values()))
        _stage_method_code(workspace, list(pool.values()))
        # A single-batch pool has nothing to repair: one episode saw every workflow, so the
        # only decision left is which feature each primitive belongs to. A pool assembled from
        # several batches does need repair -- measured on a three-batch build, it carries
        # duplicates, mixed operations and pure-navigation entries that no batch could see.
        _stage_rules(workspace, [rules_doc], site=site)
        if errors:
            _feedback(workspace, errors)
        errors, calls = _run_episode(
            runner, level="site", workspace=workspace,
            task=_prompt(procedure, SITE=site, POOL_SIZE=len(pool), BATCH_COUNT=batch_count),
            commit=lambda extra: render_final(library, site, context, extra["proposal"]))
        print(f"  [site] attempt {attempt}: "
              f"{'rendered' if not errors else f'{len(errors)} error(s)'} ({calls} model calls)")
        if not errors:
            return
    raise ValueError(f"{site} consolidation failed after {max_attempts} attempt(s): {errors}")


def build_site(runner_factory, *, site: str, workflows: list[dict], library: Path, runs: Path,
               batch_size: int, seed: int, max_attempts: int, model_config: str = "") -> dict:
    library.mkdir(parents=True, exist_ok=True)
    batches = partition_workflows(workflows, batch_size=batch_size, seed=seed)
    ctx.dump(library / "config.json", {
        "site": site, "batch_size": batch_size, "shuffle_seed": seed, "group_by": "site",
        "order_before_shuffle": ["template_id", "task_id"], "driver": "skill_agent.build",
        "orchestration": "agent-driven",
    })
    ctx.dump(library / "workflow_order.json", {"batches": [
        [{"id": x["id"], "task_id": x.get("task_id"), "template_id": x.get("template_id")}
         for x in batch] for batch in batches]})

    all_workflows = {str(x["id"]): x for x in workflows}
    for number, batch in enumerate(batches):
        _episode_env(library, number, model_config)
        run_batch(runner_factory(library, number), site=site, batch=batch, number=number,
                  all_workflows=all_workflows, library=library, runs=runs,
                  max_attempts=max_attempts)
    _episode_env(library, len(batches), model_config)
    run_site(runner_factory(library, len(batches)), site=site, all_workflows=all_workflows,
             library=library, runs=runs, max_attempts=max_attempts, batch_count=len(batches))

    index = ctx.load(library / "final_candidate" / "index.json")
    return {"site": site, "status": index["status"], "batch_count": len(batches),
            "pre_consolidation_count": len(ctx.load_pool(library)),
            "final_count": len(index["primitives"]),
            "package": str(library / "final_candidate" / "package.py")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflows", required=True,
                        help="Directory of frozen <site>.json workflow snapshots")
    parser.add_argument("--output", required=True, help="Library output directory")
    parser.add_argument("--model-config", required=True,
                        help="Webwright model YAML used for every episode")
    parser.add_argument("--sites", nargs="*", help="Optional site subset")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260810)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--runs", default=None,
                        help="Episode workspace root (default: <output>/agent_runs)")
    args = parser.parse_args(argv)

    workflow_dir = Path(args.workflows)
    output_root = Path(args.output)
    runs_root = Path(args.runs) if args.runs else output_root / "agent_runs"

    def runner_factory(library: Path, number: int) -> WebwrightRunner:
        return WebwrightRunner(
            model_config=args.model_config, repo_root=REPO_ROOT,
            command_timeout_seconds=COMMAND_TIMEOUT_SECONDS,
            extra_specs=(
                env_spec(ctx.ENV_LIBRARY, library),
                env_spec(ctx.ENV_BATCH, number),
                env_spec(ctx.ENV_MODEL_CONFIG, args.model_config),
                env_spec(ctx.ENV_REPO_ROOT, REPO_ROOT),
            ),
        )

    sites = sorted(p.stem for p in workflow_dir.glob("*.json") if p.stem != "MANIFEST")
    if args.sites:
        sites = [s for s in sites if s in set(args.sites)]

    summary = {"status": "candidate", "promoted": False, "driver": "agentic", "sites": {}}
    for site in sites:
        workflows = ctx.load(workflow_dir / f"{site}.json")
        print(f"[{site}] {len(workflows)} workflow(s)")
        summary["sites"][site] = build_site(
            runner_factory, site=site, workflows=workflows,
            library=output_root / site, runs=runs_root / site,
            batch_size=args.batch_size, seed=args.seed, max_attempts=args.max_attempts,
            model_config=args.model_config)
    ctx.dump(output_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
