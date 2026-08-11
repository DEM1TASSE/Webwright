"""Driver: run the audited primitive build as a sequence of terminal-agent episodes.

Structurally this mirrors ``webwright.skill_factory.audited_primitive_build.build_audited_site_library``
one-for-one — same batching, same validators, same apply/consolidate/render steps, same on-disk
artifact layout — with each ``llm_json`` call replaced by an agent episode in its own workspace.
That means an agentic library and a scripted library can be diffed directly.

    PYTHONPATH=src:. python -m skill_agent.build \
        --workflows skill_agent/inputs/workflows \
        --output runs/agentic_v1 \
        --model-config /path/to/model_gateway.yaml

Resumable: a stage whose ``validation.json`` already reports accepted is skipped on re-run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
    validate_extraction,
    validate_quality_verdicts,
    write_candidate_review,
)
from webwright.skill_factory.site_package_candidate import expected_class_name

from .portability import fstring_quote_reuse, make_portable
from .runner import AgentRunner, WebwrightRunner
from .stages import STAGES

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

MAX_OUTPUT_TOKENS = {"extract": 8000, "build": 16000, "quality": 8000, "consolidate": 16000}


def _dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _prompt(stage: str, **substitutions: object) -> str:
    text = (PROMPT_DIR / STAGES[stage].prompt).read_text(encoding="utf-8")
    for key, value in substitutions.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def _stage_workspace(root: Path, *parts: str) -> Path:
    workspace = root.joinpath(*parts)
    if workspace.exists():
        shutil.rmtree(workspace)
    (workspace / "in").mkdir(parents=True, exist_ok=True)
    (workspace / "out").mkdir(parents=True, exist_ok=True)
    return workspace


def _write_sources(workspace: Path, workflows: list[dict]) -> None:
    sources = workspace / "in" / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    for workflow in workflows:
        (sources / f"{workflow['id']}.py").write_text(workflow["code"], encoding="utf-8")


def _write_method_code(workspace: Path, primitives: list[dict]) -> None:
    """Extract method bodies so the agent can read code without parsing JSON strings."""
    code_dir = workspace / "in" / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    for primitive in primitives:
        if primitive.get("method") and primitive.get("method_code"):
            (code_dir / f"{primitive['method']}.py").write_text(
                primitive["method_code"], encoding="utf-8"
            )


def _feedback(workspace: Path, errors: list[str], artifact: str) -> None:
    """A rejected attempt leaves its errors in the next workspace, like the scripted retry did."""
    _dump(workspace / "in" / "previous_attempt_feedback.json", {
        "retry_instruction": (
            f"A previous attempt at this stage was rejected. Regenerate the complete "
            f"{artifact}; correct every error below without inventing code or evidence."
        ),
        "validation_feedback": errors,
    })


def _run_stage(
    runner: AgentRunner, stage: str, workspace: Path, task: str,
) -> tuple[dict, list[str], dict]:
    episode = runner.run_episode(
        stage=stage,
        task=task,
        workspace=workspace,
        step_limit=STAGES[stage].step_limit,
        max_output_tokens=MAX_OUTPUT_TOKENS[stage],
    )
    artifact, errors = STAGES[stage].validate(workspace)
    if episode.error:
        errors = [f"episode failed: {episode.error}", *errors]
    return artifact, errors, episode.to_json()


def run_extract(runner: AgentRunner, *, site: str, workflow: dict, output: Path, runs: Path,
                max_attempts: int) -> dict:
    directory = output / "extractions" / str(workflow["id"])
    existing = directory / "validation.json"
    if existing.exists() and _load(existing).get("accepted") is True:
        print(f"  [extract] {workflow['id']}: cached")
        return _load(directory / "extraction.json")

    context = {"site": site, "workflow": workflow}
    _dump(directory / "input.json", context)
    attempts, artifact, errors = [], {}, []
    for attempt in range(1, max_attempts + 1):
        workspace = _stage_workspace(runs, "extract", str(workflow["id"]), f"attempt_{attempt}")
        _dump(workspace / "in" / "context.json", context)
        _write_sources(workspace, [workflow])
        if errors:
            _feedback(workspace, errors, "out/extraction.json")
        task = _prompt("extract", SITE=site, WORKFLOW_ID=workflow["id"],
                       TASK_ID=workflow.get("task_id"), TEMPLATE_ID=workflow.get("template_id"))
        artifact, errors, episode = _run_stage(runner, "extract", workspace, task)
        attempts.append({"attempt": attempt, "proposal": artifact, "errors": errors,
                         "episode": episode})
        print(f"  [extract] {workflow['id']} attempt {attempt}: "
              f"{'accepted' if not errors else f'{len(errors)} error(s)'}")
        if not errors:
            break
    _dump(directory / "attempts.json", attempts)
    _dump(directory / "extraction.json", artifact)
    _dump(directory / "validation.json", {"accepted": not errors, "errors": errors})
    if errors:
        raise ValueError(f"{site} extraction {workflow['id']} rejected: {errors}")
    return artifact


def run_build_batch(runner: AgentRunner, *, site: str, batch: list[dict], number: int,
                    pool: dict, extractions: list[dict], all_workflows: dict, output: Path,
                    runs: Path, max_attempts: int) -> list[dict]:
    directory = output / "batches" / f"batch_{number:03d}"
    catalog_index = [{key: value.get(key) for key in (
        "primitive_id", "method", "capability", "input_contract", "output_contract",
        "supported_patterns")} for value in pool.values()]
    retrieved = retrieve_pool(batch, pool)
    # `pool` and `all_workflows` are extra compared to the scripted input: the checker runs
    # inside the workspace, so it needs the same state the scripted driver held in memory.
    context = {"site": site, "batch": batch, "extractions": extractions,
               "catalog_index": catalog_index, "retrieved_primitives": retrieved,
               "pool": list(pool.values()), "all_workflows": all_workflows}
    _dump(directory / "input.json", {"site": site, "batch": batch, "extractions": extractions,
                                     "catalog_index": catalog_index,
                                     "retrieved_primitives": retrieved})

    attempts, accepted, errors = [], [], []
    for attempt in range(1, max_attempts + 1):
        workspace = _stage_workspace(runs, "build", f"batch_{number:03d}", f"attempt_{attempt}")
        _dump(workspace / "in" / "context.json", context)
        _write_sources(workspace, batch)
        _write_method_code(workspace, list(pool.values()))
        # extractions are in batch order; a SKIP extraction has no candidate to name it by.
        for workflow, extraction in zip(batch, extractions):
            _dump(workspace / "in" / "extractions" / f"{workflow['id']}.json", extraction)
        if errors:
            _feedback(workspace, errors, "out/proposal.json")
        task = _prompt("build", SITE=site, BATCH_SIZE=len(batch),
                       WORKFLOW_IDS=", ".join(str(x["id"]) for x in batch))
        artifact, errors, episode = _run_stage(runner, "build", workspace, task)

        quality: dict = {}
        quality_episode: dict = {}
        if not errors:
            accepted, errors = validate_build_proposal(
                artifact, site=site, batch=batch, pool=pool,
                all_workflows=all_workflows, extractions=extractions,
            )
        if not errors:
            quality, quality_errors, quality_episode = run_quality(
                runner, site=site, proposal=artifact, extractions=extractions,
                batch=batch, runs=runs, number=number, attempt=attempt,
                max_attempts=max_attempts,
            )
            errors = quality_errors
        attempts.append({"attempt": attempt, "proposal": artifact, "quality_verdicts": quality,
                         "errors": errors, "episode": episode, "quality_episode": quality_episode})
        print(f"  [build] batch {number} attempt {attempt}: "
              f"{'accepted' if not errors else f'{len(errors)} error(s)'}")
        if not errors:
            break

    _dump(directory / "attempts.json", attempts)
    _dump(directory / "proposal.json", attempts[-1]["proposal"])
    _dump(directory / "validation.json", {"accepted": not errors, "errors": errors})
    _dump(directory / "workflow_attribution.json",
          attempts[-1]["proposal"].get("workflow_attribution") or [])
    if errors:
        raise ValueError(f"{site} batch {number} rejected: {errors}")
    return accepted


# A malformed or incomplete verdicts file is the gate agent failing at its own job; a
# well-formed file full of FAILs is the gate doing its job. Only the first kind should cost
# the build stage a regeneration.
_ARTIFACT_DEFECTS = ("missing artifact", "is not valid JSON", "must be a JSON object",
                     "episode failed", "must cover every")


def _is_artifact_defect(error: str) -> bool:
    return any(marker in error for marker in _ARTIFACT_DEFECTS)


def run_quality(runner: AgentRunner, *, site: str, proposal: dict, extractions: list[dict],
                batch: list[dict], runs: Path, number: int, attempt: int,
                max_attempts: int) -> tuple[dict, list[str], dict]:
    """The gate runs as its own episode: a fresh context that did not write the code it judges."""
    operations = proposal.get("operations") or []
    candidate_attribution = proposal.get("candidate_attribution") or []
    context = {"review_kind": "primitive_boundary_quality", "site": site,
               "operations": operations, "candidate_attribution": candidate_attribution,
               "extractions": extractions}

    artifact, errors, episode = {}, [], {}
    for gate_attempt in range(1, max_attempts + 1):
        workspace = _stage_workspace(
            runs, "quality", f"batch_{number:03d}", f"attempt_{attempt}_gate_{gate_attempt}")
        _dump(workspace / "in" / "context.json", context)
        _write_sources(workspace, batch)
        _write_method_code(
            workspace, [op["replacement"] for op in operations if op.get("replacement")])
        if errors:
            _feedback(workspace, errors, "out/verdicts.json")
        task = _prompt("quality", SITE=site)
        artifact, errors, episode = _run_stage(runner, "quality", workspace, task)
        if not errors:
            errors = validate_quality_verdicts(artifact, operations, candidate_attribution)
        defects = [e for e in errors if _is_artifact_defect(e)]
        print(f"  [quality] batch {number} attempt {attempt}.{gate_attempt}: "
              f"{'accepted' if not errors else f'{len(errors)} error(s)'}"
              f"{' (gate artifact defect, retrying the gate)' if defects else ''}")
        if not defects:
            break
    return artifact, errors, episode


def run_consolidate(runner: AgentRunner, *, site: str, pool: dict, all_workflows: dict,
                    output: Path, runs: Path, max_attempts: int) -> tuple[list[dict], dict, dict]:
    # `pool` is what the in-workspace checker reads; the driver artifact keeps the scripted
    # `primitive_pool` key so the two libraries stay diffable. Don't ship both to the agent —
    # the pool carries every method body and duplicating it doubles the episode's context.
    context = {"site": site, "pool": list(pool.values()), "workflows": all_workflows}
    _dump(output / "consolidation" / "input.json",
          {"site": site, "primitive_pool": list(pool.values())})

    attempts, final, errors, coverage, artifact = [], [], [], {}, {}
    for attempt in range(1, max_attempts + 1):
        workspace = _stage_workspace(runs, "consolidate", f"attempt_{attempt}")
        _dump(workspace / "in" / "context.json", context)
        _write_sources(workspace, list(all_workflows.values()))
        _write_method_code(workspace, list(pool.values()))
        if errors:
            _feedback(workspace, errors, "out/proposal.json")
        task = _prompt("consolidate", SITE=site, POOL_SIZE=len(pool))
        artifact, errors, episode = _run_stage(runner, "consolidate", workspace, task)
        if not errors:
            final, errors, coverage = validate_consolidation(
                artifact, site=site, pool=pool, workflows=all_workflows
            )
        attempts.append({"attempt": attempt, "proposal": artifact, "errors": errors,
                         "episode": episode})
        print(f"  [consolidate] attempt {attempt}: "
              f"{'accepted' if not errors else f'{len(errors)} error(s)'}")
        if not errors:
            break

    _dump(output / "consolidation" / "attempts.json", attempts)
    _dump(output / "consolidation" / "proposal.json", artifact)
    _dump(output / "consolidation" / "validation.json", {"accepted": not errors, "errors": errors})
    _dump(output / "consolidation" / "coverage.json", coverage)
    if errors:
        raise ValueError(f"{site} consolidation rejected: {errors}")
    return final, coverage, artifact


def build_site(runner: AgentRunner, *, site: str, workflows: list[dict], output: Path,
               runs: Path, batch_size: int, seed: int, max_attempts: int) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    batches = partition_workflows(workflows, batch_size=batch_size, seed=seed)
    _dump(output / "config.json", {
        "site": site, "batch_size": batch_size, "shuffle_seed": seed, "group_by": "site",
        "order_before_shuffle": ["template_id", "task_id"], "driver": "skill_agent.build",
    })
    _dump(output / "workflow_order.json", {"batches": [
        [{"id": x["id"], "task_id": x.get("task_id"), "template_id": x.get("template_id")}
         for x in batch] for batch in batches]})

    all_workflows = {str(x["id"]): x for x in workflows}
    extractions_by_workflow = {
        str(workflow["id"]): run_extract(runner, site=site, workflow=workflow, output=output,
                                         runs=runs, max_attempts=max_attempts)
        for workflow in workflows
    }

    pool: dict[str, dict] = {}
    history = []
    for number, batch in enumerate(batches):
        accepted = run_build_batch(
            runner, site=site, batch=batch, number=number, pool=pool,
            extractions=[extractions_by_workflow[str(x["id"])] for x in batch],
            all_workflows=all_workflows, output=output, runs=runs, max_attempts=max_attempts,
        )
        pool, diff = apply_build_operations(pool, accepted)
        directory = output / "batches" / f"batch_{number:03d}"
        _dump(directory / "primitive_diff.json", diff)
        _dump(directory / "snapshot" / "primitive_pool.json", list(pool.values()))
        for primitive in pool.values():
            (directory / "snapshot" / "code").mkdir(parents=True, exist_ok=True)
            (directory / "snapshot" / "code" / f"{primitive['method']}.py").write_text(
                primitive["method_code"], encoding="utf-8")
        history.append({"batch": number, "workflows": [x["id"] for x in batch], "diff": diff})

    _dump(output / "pre_consolidation" / "primitive_pool.json", list(pool.values()))
    final, coverage, raw = run_consolidate(
        runner, site=site, pool=pool, all_workflows=all_workflows,
        output=output, runs=runs, max_attempts=max_attempts,
    )

    # render_site_package round-trips through ast.unparse, which on 3.12 normalizes string
    # literals to single quotes and can turn the agent's portable f"{p['lon']}" into
    # 3.12-only f'{p['lon']}'. Repair it here, after rendering — the agent cannot.
    code, portability_notes = make_portable(render_site_package(site, final))
    if fstring_quote_reuse(code):
        raise ValueError(f"{site} rendered package is not parsable before Python 3.12 and could "
                         f"not be repaired: {fstring_quote_reuse(code)}")
    for note in portability_notes:
        print(f"  [render] {note}")
    final_dir = output / "final_candidate"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "package.py").write_text(code, encoding="utf-8")
    _dump(final_dir / "index.json", {
        "schema_version": 1, "status": "candidate", "approved": False, "site": site,
        "root_class": expected_class_name(site), "primitives": final,
        "package_sha256": "sha256:" + hashlib.sha256(code.encode()).hexdigest()})
    _dump(final_dir / "primitive_pool.json", final)
    write_candidate_review(final_dir, site=site, primitives=final)
    _dump(output / "audit.json", {
        "site": site, "status": "candidate", "history": history,
        "consolidation_operations": raw.get("operations") or [], "coverage": coverage,
        "portability_notes": portability_notes})
    return {"site": site, "status": "candidate", "batch_count": len(batches),
            "pre_consolidation_count": len(pool), "final_count": len(final),
            "portability_notes": portability_notes,
            "package": str(final_dir / "package.py")}


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
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--runs", default=None,
                        help="Episode workspace root (default: <output>/agent_runs)")
    args = parser.parse_args(argv)

    workflow_dir = Path(args.workflows)
    output_root = Path(args.output)
    runs_root = Path(args.runs) if args.runs else output_root / "agent_runs"
    runner = WebwrightRunner(model_config=args.model_config, repo_root=REPO_ROOT)

    sites = sorted(p.stem for p in workflow_dir.glob("*.json") if p.stem != "MANIFEST")
    if args.sites:
        sites = [s for s in sites if s in set(args.sites)]

    summary = {"status": "candidate", "promoted": False, "driver": "agentic", "sites": {}}
    for site in sites:
        workflows = _load(workflow_dir / f"{site}.json")
        print(f"[{site}] {len(workflows)} workflow(s)")
        summary["sites"][site] = build_site(
            runner, site=site, workflows=workflows,
            output=output_root / site, runs=runs_root / site,
            batch_size=args.batch_size, seed=args.seed, max_attempts=args.max_attempts,
        )
    _dump(output_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
