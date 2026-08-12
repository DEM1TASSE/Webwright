"""Is what I have acceptable yet?

    python -m skill_agent.verify

The only command the agent needs. It reports what this episode still owes, composes the
proposal from the per-operation files, validates everything against the shared pipeline
validators, and — once the structure is clean — submits it to an independent judge.

Exit 0 means the episode is done and the driver can commit it. Anything else prints the full
list of what is missing or wrong.

Committing to the library is deliberately *not* here. Applying operations and rendering the
package involve no judgement, so they belong to the driver, which re-runs this same check
before writing anything.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

from webwright.skill_factory.audited_primitive_build import (
    validate_build_proposal,
    validate_consolidation,
    validate_extraction,
    validate_quality_verdicts,
)

from . import context as ctx
from .portability import check_primitives

JUDGE_STEP_LIMIT = 25
JUDGE_MAX_OUTPUT_TOKENS = 8000


# --------------------------------------------------------------------------- composition
def _inline_code(primitive: dict, out_dir: Path, where: str, errors: list[str]) -> dict:
    """A method body is written as a real .py file and referenced, not escaped into JSON."""
    if not isinstance(primitive, dict):
        errors.append(f"{where}: expected an object, got {type(primitive).__name__}")
        return primitive
    code_file = primitive.pop("method_code_file", None)
    if code_file is None:
        if not primitive.get("method_code"):
            errors.append(f"{where}: needs either method_code or method_code_file")
        return primitive
    if primitive.get("method_code"):
        errors.append(f"{where}: sets both method_code and method_code_file; keep only one")
        return primitive
    resolved = (out_dir / str(code_file)).resolve()
    try:
        resolved.relative_to(out_dir.resolve())
    except ValueError:
        errors.append(f"{where}: method_code_file must stay inside out/ ({code_file})")
        return primitive
    if not resolved.is_file():
        errors.append(f"{where}: method_code_file not found: {code_file}")
        return primitive
    primitive["method_code"] = resolved.read_text(encoding="utf-8")
    return primitive


def compose(workspace: Path) -> tuple[dict, list[str], list[dict]]:
    """Build the proposal from out/ops/*.json + out/code/*.py.

    Operation index is the sorted order of the operation files; the map is reported so
    attribution indices can be checked against it.
    """
    out_dir = (Path(workspace) / "out").resolve()
    ops_dir = out_dir / "ops"
    if not ops_dir.is_dir() or not sorted(ops_dir.glob("*.json")):
        return {}, [f"write one JSON file per operation under out/ops/ (none found)"], []

    errors: list[str] = []
    operations, index_map = [], []
    for index, path in enumerate(sorted(ops_dir.glob("*.json"))):
        try:
            op = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"out/ops/{path.name}: invalid JSON: {exc}")
            continue
        if not isinstance(op, dict):
            errors.append(f"out/ops/{path.name}: must contain a JSON object")
            continue
        op = copy.deepcopy(op)
        if "replacement" in op:
            op["replacement"] = _inline_code(
                op["replacement"], out_dir, f"operation {index} replacement", errors)
        if isinstance(op.get("replacements"), list):
            op["replacements"] = [
                _inline_code(item, out_dir, f"operation {index} replacements[{i}]", errors)
                for i, item in enumerate(op["replacements"])]
        operations.append(op)
        replacement = op.get("replacement") or {}
        index_map.append({"operation_index": index, "file": path.name,
                          "op": op.get("op") or "?",
                          "primitive_id": replacement.get("primitive_id") or op.get("source") or ""})

    proposal: dict = {"operations": operations}
    for key in ("workflow_attribution", "candidate_attribution"):
        path = out_dir / f"{key}.json"
        if path.is_file():
            try:
                proposal[key] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"out/{key}.json: invalid JSON: {exc}")
    return proposal, errors, index_map


def _replacements(proposal: dict) -> list[dict]:
    found = []
    for op in proposal.get("operations") or []:
        if isinstance(op.get("replacement"), dict):
            found.append(op["replacement"])
        found.extend(x for x in (op.get("replacements") or []) if isinstance(x, dict))
    return found


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# --------------------------------------------------------------------------- independent judge
def judge(workspace: Path, proposal: dict, context: dict) -> tuple[dict, list[str]]:
    """Run a fresh judge episode over this proposal, reusing a verdict for unchanged work.

    The judge is a separate agent with an empty context. Letting the author grade its own work
    loses exactly what this catches: task-level filtering or formatting living inside a
    primitive, and record schemas narrowed to whatever the source task happened to need.
    """
    from .runner import WebwrightRunner

    workspace = Path(workspace)
    fingerprint = _digest(proposal)
    cached = workspace / "out" / "verdicts.json"
    meta = workspace / "out" / "verdicts.meta.json"
    if cached.is_file() and meta.is_file():
        if ctx.load(meta).get("proposal_sha256") == fingerprint:
            return ctx.load(cached), []

    gate_dir = workspace / ".judge"
    attempt = max([int(p.name.split("_")[-1]) for p in gate_dir.glob("attempt_*")], default=0) + 1
    judge_ws = gate_dir / f"attempt_{attempt:03d}"
    (judge_ws / "in").mkdir(parents=True, exist_ok=True)
    (judge_ws / "out").mkdir(parents=True, exist_ok=True)

    operations = proposal.get("operations") or []
    ctx.dump(judge_ws / "in" / "context.json", {
        "mode": "judge", "review_kind": "primitive_boundary_quality", "site": context["site"],
        "operations": operations,
        "candidate_attribution": proposal.get("candidate_attribution") or [],
        "extractions": ctx.load_extractions(workspace, batch=context.get("batch") or [])})
    if (workspace / "in" / "sources").is_dir():
        shutil.copytree(workspace / "in" / "sources", judge_ws / "in" / "sources", dirs_exist_ok=True)
    code_dir = judge_ws / "in" / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    for op in operations:
        replacement = op.get("replacement") if isinstance(op, dict) else None
        if isinstance(replacement, dict) and replacement.get("method") and replacement.get("method_code"):
            (code_dir / f"{replacement['method']}.py").write_text(
                replacement["method_code"], encoding="utf-8")

    prompt = (ctx.repo_root() / "skill_agent" / "prompts" / "judge.md").read_text(encoding="utf-8")
    episode = WebwrightRunner(model_config=ctx.model_config(), repo_root=ctx.repo_root()).run_episode(
        stage="judge", task=prompt.replace("{{SITE}}", context["site"]), workspace=judge_ws,
        step_limit=JUDGE_STEP_LIMIT, max_output_tokens=JUDGE_MAX_OUTPUT_TOKENS)

    verdict_path = judge_ws / "out" / "verdicts.json"
    if not verdict_path.is_file():
        return {}, [f"the judge episode produced no verdicts ({episode.exit_status})"
                    + (f": {episode.error}" if episode.error else "")]
    verdicts = ctx.load(verdict_path)
    ctx.dump(cached, verdicts)
    ctx.dump(meta, {"proposal_sha256": fingerprint, "judge_workspace": str(judge_ws.name)})
    return verdicts, []


# --------------------------------------------------------------------------- verification
def verify_batch(workspace: Path, context: dict, *, with_judge: bool) -> tuple[list[str], list[str], dict]:
    steps, errors = [], []
    batch = context.get("batch") or []

    for workflow in batch:
        wid = str(workflow["id"])
        path = workspace / "out" / "extractions" / f"{wid}.json"
        if not path.is_file():
            steps.append(f"[ ] extract {wid} — out/extractions/{wid}.json does not exist")
            errors.append(f"extract {wid}: out/extractions/{wid}.json does not exist")
            continue
        try:
            found = validate_extraction(ctx.load(path), workflow=workflow)
        except json.JSONDecodeError as exc:
            found = [f"out/extractions/{wid}.json is not valid JSON: {exc}"]
        steps.append(f"{'[x]' if not found else '[ ]'} extract {wid}"
                     + (f" — {len(found)} error(s)" if found else ""))
        errors.extend(f"extract {wid}: {e}" for e in found)
    if errors:
        steps.append("[ ] build — blocked until every workflow is extracted")
        return steps, errors, {}

    proposal, compose_errors, index_map = compose(workspace)
    if compose_errors:
        steps.append(f"[ ] build — {len(compose_errors)} composition error(s)")
        return steps, compose_errors, {}

    _, build_errors = validate_build_proposal(
        proposal, site=context["site"], batch=batch, pool=ctx.load_pool(),
        all_workflows={str(k): v for k, v in (context.get("all_workflows") or {}).items()},
        extractions=ctx.load_extractions(workspace, batch=batch))
    build_errors = list(build_errors) + check_primitives(_replacements(proposal))
    steps.append(f"{'[x]' if not build_errors else '[ ]'} build — {len(proposal['operations'])} "
                 f"operation(s)" + (f", {len(build_errors)} error(s)" if build_errors else ""))
    if build_errors:
        return steps, build_errors, {"index_map": index_map}
    if not with_judge:
        steps.append("[-] judge — skipped")
        return steps, [], {"proposal": proposal, "index_map": index_map}

    verdicts, judge_errors = judge(workspace, proposal, context)
    if judge_errors:
        steps.append("[ ] judge — did not complete")
        return steps, judge_errors, {"proposal": proposal, "index_map": index_map}
    verdict_errors = validate_quality_verdicts(
        verdicts, proposal.get("operations") or [], proposal.get("candidate_attribution") or [])
    steps.append(f"{'[x]' if not verdict_errors else '[ ]'} judge"
                 + (f" — {len(verdict_errors)} unresolved" if verdict_errors else " — all passed"))
    return steps, verdict_errors, {"proposal": proposal, "verdicts": verdicts,
                                   "index_map": index_map}


def verify_judge(workspace: Path, context: dict, **_) -> tuple[list[str], list[str], dict]:
    """The judge checks its own verdicts with the same command everyone else uses."""
    path = Path(workspace) / "out" / "verdicts.json"
    if not path.is_file():
        return ["[ ] verdicts — out/verdicts.json does not exist"], \
               ["write out/verdicts.json covering every operation and every REJECT"], {}
    try:
        verdicts = ctx.load(path)
    except json.JSONDecodeError as exc:
        return ["[ ] verdicts — invalid JSON"], [f"out/verdicts.json is not valid JSON: {exc}"], {}
    errors = validate_quality_verdicts(
        verdicts, context.get("operations") or [], context.get("candidate_attribution") or [])
    # A FAIL verdict is a legitimate ruling, not a defect in the verdict file. The gate check
    # reports those to the author; here only coverage and shape matter.
    shape = [e for e in errors if not e.startswith("quality gate rejected")]
    return [f"{'[x]' if not shape else '[ ]'} verdicts — {len(verdicts.get('verdicts') or [])} "
            f"operation ruling(s)"], shape, {}


def verify_site(workspace: Path, context: dict, **_) -> tuple[list[str], list[str], dict]:
    pool = ctx.load_pool()
    steps = [f"pool holds {len(pool)} primitive(s)"]
    proposal, compose_errors, index_map = compose(workspace)
    if compose_errors:
        steps.append(f"[ ] consolidate — {len(compose_errors)} composition error(s)")
        return steps, compose_errors, {}
    final, errors, _ = validate_consolidation(
        proposal, site=context["site"], pool=pool,
        workflows={str(k): v for k, v in (context.get("workflows") or {}).items()})
    errors = list(errors) + check_primitives(_replacements(proposal))
    steps.append(f"{'[x]' if not errors else '[ ]'} consolidate — {len(pool)} pooled -> "
                 f"{len(final)} final" + (f", {len(errors)} error(s)" if errors else ""))
    return steps, errors, {"proposal": proposal, "index_map": index_map}


def run(workspace: Path, *, with_judge: bool = True) -> tuple[int, list[str], list[str], dict]:
    workspace = Path(workspace).resolve()
    context = ctx.load_context(workspace)
    verifier = {"site": verify_site, "judge": verify_judge}.get(
        context.get("mode", "batch"), verify_batch)
    steps, errors, extra = verifier(workspace, context, with_judge=with_judge)
    return (0 if not errors else 1), steps, errors, extra


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default=".", help="episode workspace (default: cwd)")
    parser.add_argument("--no-judge", action="store_true",
                        help="skip the independent judge (structural checks only)")
    args = parser.parse_args(argv)
    try:
        code, steps, errors, extra = run(Path(args.workspace), with_judge=not args.no_judge)
    except (ctx.MissingState, FileNotFoundError) as exc:
        print(json.dumps({"ready": False, "errors": [str(exc)]}, indent=2))
        return 2

    print("\n".join(steps))
    if extra.get("index_map"):
        print("\nOperation index (sorted order of out/ops/*.json):")
        for row in extra["index_map"]:
            print(f"  [{row['operation_index']}] {row['file']:<28} {row['op']:<8} {row['primitive_id']}")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for error in errors:
            print(f"  - {error}")
        print("\nNOT READY. Fix these and run this command again.")
    else:
        print("\nREADY: everything this episode owes is present and accepted. Set done=true.")
    return code


if __name__ == "__main__":
    sys.exit(main())
