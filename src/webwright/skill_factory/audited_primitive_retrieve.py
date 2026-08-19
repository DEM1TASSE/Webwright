"""Metadata-first retrieval from an audited candidate site package."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .audited_primitive_build import render_site_package


@dataclass
class AuditedRetrieval:
    site: str
    decision: str = "skip"
    primitives: list[dict] = field(default_factory=list)
    reason: str = ""
    remaining_gap: list[str] = field(default_factory=list)
    scratch_plan: dict | None = None
    patches: list[dict] = field(default_factory=list)
    contract_verdict: dict = field(default_factory=dict)

    @property
    def sources(self):
        return [{"primitive_id": x["primitive_id"], "content_hash": primitive_hash(x)}
                for x in self.primitives]


def primitive_hash(primitive: dict) -> str:
    return "sha256:" + hashlib.sha256(primitive["method_code"].encode()).hexdigest()


def load_candidate_index(library: str | Path, site: str) -> dict:
    path = Path(library) / site / "final_candidate" / "index.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("site") != site or value.get("status") != "candidate":
        raise ValueError(f"invalid audited candidate index: {path}")
    return value


def draft_scratch_plan(
    task: str, *, site: str, plan_fn: Callable[[str, str], dict] | None = None,
) -> dict:
    """Plan without library exposure so later retrieval can only propose local substitutions."""
    if plan_fn is None:
        from .llm import llm_json

        def plan_fn(current_task, current_site):
            return llm_json(
                "Create a concise scratch-first web-task plan without assuming any skill or "
                "library exists. Return JSON with steps and required_facts. Each step must have "
                "a stable id like S1, an action, inputs, outputs, and acceptance_checks. Separate "
                "website fact acquisition from filtering, aggregation, and output formatting. "
                "Do not mention primitives. Schema: {\"steps\":[{\"id\":\"S1\",\"action\":\"...\","
                "\"inputs\":[],\"outputs\":[],\"acceptance_checks\":[]}],"
                "\"required_facts\":[{\"id\":\"...\",\"needed_by_step\":\"S1\","
                "\"description\":\"...\"}]}",
                json.dumps({"site": current_site, "task": current_task}, ensure_ascii=False),
            )

    raw = plan_fn(task, site) or {}
    steps = []
    seen = set()
    for item in raw.get("steps") or []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        action = str(item.get("action") or "").strip()
        if not sid or not action or sid in seen:
            continue
        seen.add(sid)
        steps.append({
            "id": sid,
            "action": action,
            "inputs": [str(x) for x in item.get("inputs") or []],
            "outputs": [str(x) for x in item.get("outputs") or []],
            "acceptance_checks": [str(x) for x in item.get("acceptance_checks") or []],
        })
    if not steps:
        steps = [{"id": "S1", "action": "Solve the task from scratch", "inputs": [],
                  "outputs": ["required answer facts"], "acceptance_checks": []}]
    facts = []
    for item in raw.get("required_facts") or []:
        if isinstance(item, dict) and item.get("id"):
            facts.append({key: str(item.get(key) or "") for key in
                          ("id", "needed_by_step", "description")})
    return {"site": site, "task": task, "steps": steps, "required_facts": facts}


def render_frozen_scratch_plan(plan: dict) -> str:
    return "\n".join([
        "## Frozen scratch-first plan",
        "This plan was produced before any library material was visible. Preserve its overall "
        "strategy. Library material may only replace a specifically declared step; all other "
        "steps remain the scratch solution.",
        "```json", json.dumps(plan, ensure_ascii=False, indent=2), "```", "",
    ])


def retrieve_audited_primitives(
    task: str, library: str | Path, *, site: str, max_primitives: int = 5,
    decide_fn: Callable[[str, list[dict]], dict] | None = None,
    verify_fn: Callable[[str, dict, list[dict]], dict] | None = None,
    scratch_plan: dict | None = None,
) -> AuditedRetrieval:
    index = load_candidate_index(library, site)
    primitives = index.get("primitives") or []
    metadata = [{key: primitive.get(key) for key in (
        "primitive_id", "feature", "method", "capability", "owns", "does_not_own",
        "input_contract", "output_contract", "requires", "provides", "supported_patterns",
        "guarantees",
    )} for primitive in primitives]
    if decide_fn is None:
        from .llm import llm_json

        def decide_fn(current_task, candidates):
            return llm_json(
                "Route using primitive METADATA only against a frozen scratch plan. Semantic "
                "relatedness is not usefulness. A primitive is useful only if its inputs are "
                "reachable from the task, preserved scratch work, or earlier patch outputs and it "
                "can replace a concrete sub-operation inside a named scratch step. Its output must "
                "be directly consumable by the preserved remainder of that step or a later step; "
                "it need not replace the whole step. Selected patches may form a short acyclic "
                "chain in scratch-plan order. ADAPT means local substitutions only; it must not "
                "rewrite the overall strategy. If a "
                "necessary field, entity-discovery step, completeness guarantee, or runtime "
                "precondition remains missing, preserve the original scratch step or SKIP. "
                "A patch is invalid when the original acquisition must still run unconditionally "
                "after a successful primitive call to obtain a required field, traverse the full "
                "result set, or satisfy the step's acceptance checks. Fallback must be conditional "
                "on primitive failure; it is not permission to perform both strategies every time. "
                "Prefer SKIP when a primitive only adds an extra probe without avoiding meaningful "
                "scratch work. For an open-ended nearest/all/vicinity request, a single query- or "
                "page-scoped search primitive does not replace candidate discovery. Preserve the "
                "scratch discovery step unless a selected primitive explicitly owns a sufficiently "
                "complete candidate-set acquisition; partial search may only patch later parsing, "
                "enrichment, or routing after scratch has established the candidate set. "
                "Return JSON {\"decision\":\"use|adapt|skip\",\"primitive_ids\":[],"
                "\"reason\":\"...\",\"remaining_gap\":[],\"patches\":[{"
                "\"scratch_step_id\":\"S1\",\"primitive_id\":\"...\","
                "\"replaces\":[],\"preserves\":[],\"acceptance_checks\":[],"
                "\"avoids_when_accepted\":[\"specific original work not otherwise required\"],"
                "\"fallback\":\"original scratch step\"}]}. USE requires complete acquisition "
                "coverage. ADAPT requires at least one valid local patch. Select at most five. "
                "Task filtering, aggregation, ranking, semantic decisions, and formatting remain "
                "scratch responsibilities. Never infer capabilities absent from metadata.",
                json.dumps({"task": current_task, "scratch_plan": scratch_plan,
                            "candidates": candidates}, ensure_ascii=False),
            )
    raw = decide_fn(task, metadata) or {}
    decision = str(raw.get("decision") or "skip").lower()
    if decision not in {"use", "adapt", "skip"}:
        decision = "skip"
    by_id = {x["primitive_id"]: x for x in primitives}
    selected = []
    for pid in raw.get("primitive_ids") or []:
        if pid in by_id and by_id[pid] not in selected:
            selected.append(by_id[pid])
        if len(selected) >= max_primitives:
            break
    if decision in {"use", "adapt"} and not selected:
        decision = "skip"
    if decision == "skip":
        selected = []
    step_ids = {str(x.get("id")) for x in (scratch_plan or {}).get("steps", [])}
    selected_ids = {x["primitive_id"] for x in selected}
    contract_verdict = {}
    if decision in {"use", "adapt"} and selected and verify_fn is not None:
        raw_verdict = verify_fn(task, raw, selected) or {}
        verdict = str(raw_verdict.get("verdict") or "reject").lower()
        checks = raw_verdict.get("checks") or {}
        allowed_checks = {"input_reachability", "guarantee_sufficiency",
                          "closed_acquisition"}
        checks_valid = (
            isinstance(checks, dict)
            and set(checks) == allowed_checks
            and all(value in {"pass", "fail"} for value in checks.values())
        )
        contract_verdict = {
            "verdict": verdict if verdict in {"accept", "reject"} else "reject",
            "checks": checks if checks_valid else {},
            "closed_acquisitions": [
                str(x) for x in raw_verdict.get("closed_acquisitions") or []
                if str(x).strip()
            ],
            "reason": str(raw_verdict.get("reason") or "malformed verifier output"),
        }
        if (
            contract_verdict["verdict"] != "accept"
            or not checks_valid
            or any(value != "pass" for value in checks.values())
            or not contract_verdict["closed_acquisitions"]
        ):
            decision, selected = "skip", []
            selected_ids = set()
    patches = []
    for patch in raw.get("patches") or []:
        if not isinstance(patch, dict):
            continue
        sid = str(patch.get("scratch_step_id") or "")
        pid = str(patch.get("primitive_id") or "")
        if not sid or not pid or (step_ids and sid not in step_ids) or pid not in selected_ids:
            continue
        replaces = [str(x) for x in patch.get("replaces") or [] if str(x).strip()]
        checks = [str(x) for x in patch.get("acceptance_checks") or [] if str(x).strip()]
        avoids = [str(x) for x in patch.get("avoids_when_accepted") or [] if str(x).strip()]
        # "Helpful context" is exactly the anchoring channel this mode is designed to close.
        # A local patch must replace a concrete operation and define how its output is accepted.
        if (not replaces or not checks or not avoids
                or all(item.strip() == sid or len(item.strip()) < 8 for item in replaces)):
            continue
        patches.append({
            "scratch_step_id": sid, "primitive_id": pid,
            "replaces": replaces,
            "preserves": [str(x) for x in patch.get("preserves") or []],
            "acceptance_checks": checks,
            "avoids_when_accepted": avoids,
            "fallback": str(patch.get("fallback") or "Run the original scratch step"),
        })
    if scratch_plan and decision == "adapt" and not patches:
        decision, selected = "skip", []
    elif scratch_plan and decision == "adapt":
        patched_ids = {x["primitive_id"] for x in patches}
        selected = [x for x in selected if x["primitive_id"] in patched_ids]
    if decision == "skip":
        patches = []
    return AuditedRetrieval(
        site=site, decision=decision, primitives=selected,
        reason=str(raw.get("reason") or ""),
        remaining_gap=[str(x) for x in raw.get("remaining_gap") or [] if isinstance(x, str)],
        scratch_plan=scratch_plan, patches=patches, contract_verdict=contract_verdict,
    )


def render_audited_primitive_hint(
    result: AuditedRetrieval, *, include_code: bool = True,
) -> str:
    plan_hint = render_frozen_scratch_plan(result.scratch_plan) if result.scratch_plan else ""
    if not result.primitives:
        return plan_hint
    lines = [
        plan_hint.rstrip(),
        "## Retrieved site primitives (synthesis material)",
        f"Router decision: {result.decision}. Reason: {result.reason}",
        "Primitive methods own site acquisition and typed parsing. The current workflow still "
        "owns task filtering, aggregation, ranking, semantic decisions, and answer formatting.",
        ("Preserve a `# primitive-source: <id> <hash>` comment for every method actually reused."
         if include_code else
         "Ablation condition: implementation code is withheld. Do not claim or mark primitive "
         "code usage; solve using the frozen scratch plan plus contract metadata only."),
        "Write primitive_usage.json with used primitive ids/hashes and a coverage_assessment.",
    ]
    if result.contract_verdict:
        lines.insert(3, "Contract verifier: " + json.dumps(
            result.contract_verdict, ensure_ascii=False, sort_keys=True
        ))
    if result.scratch_plan:
        lines[3:3] = [
            "Apply only the approved local patches below. Do not redesign, replace, or reorder "
            "the rest of the frozen scratch plan. " + (
                "Vendor selected code into standalone final_script.py; do not import the "
                "candidate package at runtime." if include_code else
                "No candidate implementation is available in this ablation."
            ),
            "A patched step is accepted only when every declared acceptance check passes. On an "
            "exception, empty/partial output, missing required field, or failed check, immediately "
            "run that step's original scratch method. Primitive failure is not evidence that the "
            "website fact is absent and must not be converted directly to NOT_FOUND_ERROR.",
            "Do not apply a patch when its successful output still requires the original acquisition "
            "unconditionally for missing task-required fields or completeness. In that case the "
            "primitive adds work rather than replacing work: follow the frozen scratch plan directly."
            if include_code else
            "Do not treat metadata exposure as a reason to run an extra acquisition strategy.",
            "For each actually called primitive, append one JSON object per lifecycle event to "
            "primitive_execution_trace.jsonl. Use events entered, completed, acceptance_passed, "
            "acceptance_failed, and fallback_used, and include primitive_id and scratch_step_id."
            if include_code else
            "Do not write primitive execution events because implementation code is withheld.",
        ]
    else:
        lines.insert(3, "Use only the verified closed acquisitions. Vendor selected primitive "
                     "method bodies verbatim into standalone final_script.py; ADAPT means compose "
                     "them with task-layer code, not rewrite their selectors, endpoints, filters, "
                     "pagination, or parsers. If an exact method cannot run in the chosen runtime, "
                     "do not emulate it under the original provenance marker: fall back to the "
                     "scratch acquisition. An empty primitive result is not proof of absence unless "
                     "the relevant acquisition is accepted and complete for the task scope. For an "
                     "exhaustive request, a partial acquisition that finds no qualifying candidate "
                     "must fall back to scratch discovery rather than emit a successful empty list. "
                     "For open-ended nearest/all/vicinity requests, do not let a single query- or "
                     "page-scoped primitive define the candidate set: preserve scratch candidate "
                     "discovery unless a primitive explicitly guarantees the required scope. "
                     "Preserve the goal's cardinality: wording such as 'a', 'an', or 'the nearest' "
                     "requires at most one selected entity unless the goal explicitly asks for all. "
                     "Before SUCCESS, validate every requested output field against acquired facts. "
                     "Preserve site-returned address values verbatim (for example, do not abbreviate "
                     "a full state name). If a field is absent but is unambiguously entailed by other "
                     "acquired facts, derive and record it explicitly; otherwise use scratch "
                     "enrichment or the original acquisition. Never silently emit a placeholder "
                     "value merely because the primitive response omitted the field.")
    if result.remaining_gap:
        lines.append("Router-declared remaining gaps: " + "; ".join(result.remaining_gap))
    if result.scratch_plan:
        lines.extend(["", "### Approved local patches", "```json",
                      json.dumps(result.patches, ensure_ascii=False, indent=2), "```"])
    for primitive, source in zip(result.primitives, result.sources):
        lines.extend([
            "", f"### {primitive['primitive_id']}", f"capability: {primitive['capability']}",
            f"owns: {json.dumps(primitive.get('owns') or [], ensure_ascii=False)}",
            f"does_not_own: {json.dumps(primitive.get('does_not_own') or [], ensure_ascii=False)}",
            f"input_contract: {json.dumps(primitive.get('input_contract'), ensure_ascii=False)}",
            f"output_contract: {json.dumps(primitive.get('output_contract'), ensure_ascii=False)}",
            f"# primitive-source: {source['primitive_id']} {source['content_hash']}",
        ])
    if include_code:
        lines.extend(["", "```python",
                      render_site_package(result.site, result.primitives).rstrip(), "```", ""])
    else:
        lines.extend(["", "Implementation withheld for metadata-only ablation.", ""])
    return "\n".join(lines)


def write_audited_retrieval(path: str | Path, result: AuditedRetrieval, *, task: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "task": task, "site": result.site, "decision": result.decision,
        "retrieved": result.sources, "reason": result.reason,
        "remaining_gap": result.remaining_gap, "scratch_plan": result.scratch_plan,
        "patches": result.patches, "contract_verdict": result.contract_verdict,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
