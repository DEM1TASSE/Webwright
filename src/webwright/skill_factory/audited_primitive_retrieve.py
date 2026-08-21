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
    proposal: dict = field(default_factory=dict)

    @property
    def sources(self):
        return [{"primitive_id": x["primitive_id"], "content_hash": primitive_hash(x)}
                for x in self.primitives]


def primitive_hash(primitive: dict) -> str:
    return "sha256:" + hashlib.sha256(primitive["method_code"].encode()).hexdigest()


def browser_effects(primitive: dict) -> dict:
    """Project code-level browser effects into metadata without exposing implementation code."""
    code = str(primitive.get("method_code") or "")
    owns = " ".join(str(x) for x in primitive.get("owns") or []).lower()
    navigates = (
        ("self.page.goto(" in code or "page.goto(" in code)
        or (
            any(token in code for token in (".click(", ".fill(", ".press("))
            and any(token in owns for token in ("navigate", "open ", "load ", "submit"))
        )
    )
    uses_browser_request_context = any(
        token in code for token in ("self.page.request", "page.request", ".context.request")
    )
    mutates_live_controls = any(token in code for token in (".click(", ".fill(", ".press("))
    return {
        "navigates_live_page": navigates,
        "uses_browser_request_context": uses_browser_request_context,
        "may_change_session_or_page_state": bool(
            navigates or uses_browser_request_context or mutates_live_controls
        ),
    }


def load_candidate_index(library: str | Path, site: str) -> dict:
    path = Path(library) / site / "final_candidate" / "index.json"
    if not path.is_file():
        return {
            "site": site, "status": "candidate", "approved": False,
            "primitives": [], "missing_site_package": True,
        }
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
                "For every website fact, freeze its acquisition obligation before any library is "
                "visible: coverage_obligation is single for one identified record, "
                "complete_population for all/count/extreme/absence over a population, or "
                "top_k_sound only when a source-native ordering guarantee would suffice. Also "
                "record evidence_scope as entity_current, transaction_line, page, population, "
                "or scalar. Give every fact a fact_kind: collection for an acquired population, "
                "identity for a stable subject key/name, field for one typed value, or provenance "
                "for evidence/source lineage. Keep facts atomic: never encode 'the record satisfying "
                "qualifier X' as one fact. Split it into the collection, qualifier field, stable "
                "identity/join field, requested attribute, and provenance. Keep transaction/history "
                "facts separate from current entity facts. Include identity, scope, provenance, and "
                "completeness facts needed to accept a requested value, even when they are not "
                "displayed in the final answer. Also return requested_output_facts: atomic fields "
                "explicitly requested by the goal, each with id, description, value_type, and "
                "evidence_scope. Preserve every explicit semantic head or modifier in ambiguous "
                "compound wording instead of silently dropping one. The final "
                "formatting step must project only fields explicitly requested by the task; do not "
                "add supporting counts, identifiers, or explanations unless requested. "
                "Do not mention primitives. Schema: {\"steps\":[{\"id\":\"S1\",\"action\":\"...\","
                "\"inputs\":[],\"outputs\":[],\"acceptance_checks\":[]}],"
                "\"required_facts\":[{\"id\":\"...\",\"needed_by_step\":\"S1\","
                "\"description\":\"...\",\"fact_kind\":\"collection|identity|field|provenance\","
                "\"coverage_obligation\":\"single|"
                "complete_population|top_k_sound\",\"evidence_scope\":\"entity_current|"
                "transaction_line|page|population|scalar\"}],"
                "\"requested_output_facts\":[{\"id\":\"O1\",\"description\":\"...\","
                "\"value_type\":\"string|number|money|date|duration|coordinates|list|object\","
                "\"evidence_scope\":\"entity_current|transaction_line|page|population|scalar\"}]}",
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
            fact = {key: str(item.get(key) or "") for key in
                    ("id", "needed_by_step", "description")}
            coverage = str(item.get("coverage_obligation") or "single")
            scope = str(item.get("evidence_scope") or "scalar")
            kind = str(item.get("fact_kind") or "field")
            fact["coverage_obligation"] = (
                coverage if coverage in {"single", "complete_population", "top_k_sound"}
                else "complete_population"
            )
            fact["evidence_scope"] = (
                scope if scope in {
                    "entity_current", "transaction_line", "page", "population", "scalar",
                } else "scalar"
            )
            fact["fact_kind"] = (
                kind if kind in {"collection", "identity", "field", "provenance"}
                else "field"
            )
            facts.append(fact)
    requested_output_facts = []
    for item in raw.get("requested_output_facts") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        scope = str(item.get("evidence_scope") or "scalar")
        requested_output_facts.append({
            "id": str(item.get("id")),
            "description": str(item.get("description") or ""),
            "value_type": str(item.get("value_type") or "string"),
            "evidence_scope": scope if scope in {
                "entity_current", "transaction_line", "page", "population", "scalar",
            } else "scalar",
        })
    return {
        "site": site, "task": task, "steps": steps, "required_facts": facts,
        "requested_output_facts": requested_output_facts,
    }


def _schema_node_at_path(schema: dict, path: str) -> dict | None:
    """Resolve a small JSON-schema path such as ``orders[].order_date``."""
    if not isinstance(schema, dict) or not path or path.startswith("."):
        return None
    node = schema
    for raw_part in path.split("."):
        is_array = raw_part.endswith("[]")
        part = raw_part[:-2] if is_array else raw_part
        properties = node.get("properties") if isinstance(node, dict) else None
        if not isinstance(properties, dict) or part not in properties:
            return None
        node = properties[part]
        if is_array:
            if not isinstance(node, dict) or node.get("type") != "array":
                return None
            node = node.get("items")
            if not isinstance(node, dict):
                return None
    return node if isinstance(node, dict) else None


def _primitive_satisfies_coverage(primitive: dict, obligation: str) -> bool:
    if obligation == "single":
        return True
    guarantees = primitive.get("guarantees") or {}
    if guarantees.get("completeness") == "complete":
        return True
    return obligation == "top_k_sound" and guarantees.get("top_k_sound") is True


def _binding_matches_fact_shape(node: dict, fact: dict) -> bool:
    """Enforce only planner-owned atomic shapes; legacy facts remain compatible."""
    kind = str(fact.get("fact_kind") or "")
    if not kind:
        return True
    node_type = node.get("type")
    node_types = set(node_type) if isinstance(node_type, list) else {node_type}
    if kind == "collection":
        return "array" in node_types
    return not bool(node_types & {"array", "object"})


def _contract_closed_patch(
    patch: dict, *, primitive: dict, scratch_plan: dict | None,
) -> tuple[bool, str]:
    """Check declared postconditions without trying to infer task or site semantics."""
    plan = scratch_plan or {}
    step_order = {
        str(item.get("id")): index for index, item in enumerate(plan.get("steps", []))
        if isinstance(item, dict) and item.get("id")
    }
    patch_step = str(patch.get("scratch_step_id") or "")
    patch_index = step_order.get(patch_step, -1)
    all_facts = [
        item for item in plan.get("required_facts", [])
        if isinstance(item, dict) and item.get("id")
    ]
    facts = {
        str(item.get("id")): item
        for item in all_facts
        if step_order.get(str(item.get("needed_by_step") or ""), -1) >= patch_index
    }
    # Legacy plans without structured facts remain routable. New V18 plans fail closed below.
    if not all_facts:
        return True, "legacy plan has no structured facts"

    replaced = [str(x) for x in patch.get("replaces_fact_ids") or [] if str(x).strip()]
    bindings = patch.get("output_bindings") or []
    if not replaced or not isinstance(bindings, list):
        return False, "patch does not declare replaced fact ids and output bindings"
    if any(fact_id not in facts for fact_id in replaced):
        return False, "patch references a fact before its frozen scratch step or outside the plan"

    by_fact = {}
    output_schema = primitive.get("output_contract") or {}
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        fact_id = str(binding.get("fact_id") or "")
        path = str(binding.get("path") or "")
        node = _schema_node_at_path(output_schema, path)
        if (fact_id in facts and node is not None
                and _binding_matches_fact_shape(node, facts[fact_id])):
            by_fact.setdefault(fact_id, []).append(binding)
    for fact_id in replaced:
        fact = facts[fact_id]
        if fact_id not in by_fact:
            return False, f"no schema-valid output binding for frozen fact {fact_id}"
        scope = str(fact.get("evidence_scope") or "scalar")
        if not any(str(item.get("evidence_scope") or "") == scope
                   for item in by_fact[fact_id]):
            return False, f"evidence scope mismatch for frozen fact {fact_id}"
        obligation = str(fact.get("coverage_obligation") or "single")
        if not _primitive_satisfies_coverage(primitive, obligation):
            return False, f"primitive guarantee does not satisfy {obligation} for {fact_id}"
    return True, "declared postconditions are contract-closed"


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
    if not primitives:
        return AuditedRetrieval(
            site=site, decision="skip", primitives=[],
            reason=(
                "no generated candidate package for this site"
                if index.get("missing_site_package")
                else "candidate package contains no primitives"
            ),
            scratch_plan=scratch_plan,
        )
    metadata = []
    for primitive in primitives:
        item = {key: primitive.get(key) for key in (
            "primitive_id", "feature", "method", "capability", "owns", "does_not_own",
            "input_contract", "output_contract", "requires", "provides", "supported_patterns",
            "guarantees",
        )}
        item["browser_effects"] = browser_effects(primitive)
        metadata.append(item)
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
                "Do not turn a checkable disambiguation step into an unconditional second "
                "acquisition. For a lookup or route over a finite set of fully named entities, a "
                "primitive may replace the acquisition when its output contains both the requested "
                "fact and resolved identity fields sufficient for the preserved acceptance checks. "
                "Single-entity lookup does not require population completeness when that identity "
                "match is checkable. This exception never applies when the task must first discover "
                "an open candidate set or choose nearest/all/best among unknown entities; preserve "
                "that candidate discovery before patching any downstream operator. "
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
                "\"replaces_fact_ids\":[\"F1\"],\"output_bindings\":[{\"fact_id\":\"F1\","
                "\"path\":\"records[].field\",\"evidence_scope\":\"entity_current|"
                "transaction_line|page|population|scalar\"}],"
                "\"avoids_when_accepted\":[\"specific original work not otherwise required\"],"
                "\"fallback\":\"original scratch step\"}]}. USE requires complete acquisition "
                "coverage. ADAPT requires at least one valid local patch. Select at most five. "
                "Task filtering, aggregation, ranking, semantic decisions, and formatting remain "
                "scratch responsibilities. For every replaced frozen fact, bind an actual path "
                "from that primitive's output_contract and preserve the fact's frozen evidence "
                "scope. Respect atomic fact shape: collection facts bind an array path; identity, "
                "field, and provenance facts bind concrete scalar leaves, never an array/object root. "
                "A population reducer (all/count/max/min/latest/absence) requires a complete "
                "population guarantee, or an explicit top_k_sound guarantee when that is the "
                "frozen obligation. Do not claim a continuation field or requested fact that is "
                "absent from the output schema. Never infer capabilities absent from metadata.",
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
        normalized_patch = {
            "scratch_step_id": sid, "primitive_id": pid,
            "replaces": replaces,
            "preserves": [str(x) for x in patch.get("preserves") or []],
            "acceptance_checks": checks,
            "replaces_fact_ids": [
                str(x) for x in patch.get("replaces_fact_ids") or [] if str(x).strip()
            ],
            "output_bindings": [
                {
                    "fact_id": str(item.get("fact_id") or ""),
                    "path": str(item.get("path") or ""),
                    "evidence_scope": str(item.get("evidence_scope") or ""),
                }
                for item in patch.get("output_bindings") or [] if isinstance(item, dict)
            ],
            "avoids_when_accepted": avoids,
            "fallback": str(patch.get("fallback") or "Run the original scratch step"),
        }
        closed, _closed_reason = _contract_closed_patch(
            normalized_patch, primitive=by_id[pid], scratch_plan=scratch_plan,
        )
        if not closed:
            continue
        patches.append(normalized_patch)
    if scratch_plan and decision in {"use", "adapt"} and not patches:
        decision, selected = "skip", []
    elif scratch_plan and decision in {"use", "adapt"}:
        patched_ids = {x["primitive_id"] for x in patches}
        selected = [x for x in selected if x["primitive_id"] in patched_ids]
    if decision == "skip":
        patches = []
    if scratch_plan:
        replaced_fact_ids = {
            fact_id for patch in patches for fact_id in patch.get("replaces_fact_ids") or []
        }
        remaining_gap = [
            f"{item.get('id')}: {item.get('description')}"
            for item in scratch_plan.get("required_facts") or []
            if isinstance(item, dict) and item.get("id") not in replaced_fact_ids
        ]
    else:
        remaining_gap = [
            str(x) for x in raw.get("remaining_gap") or [] if isinstance(x, str)
        ]
    return AuditedRetrieval(
        site=site, decision=decision, primitives=selected,
        reason=str(raw.get("reason") or ""),
        remaining_gap=remaining_gap,
        scratch_plan=scratch_plan, patches=patches, contract_verdict=contract_verdict,
        proposal=raw,
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
    selected_ids = {item["primitive_id"] for item in result.primitives}
    planned_calls = [
        call for call in result.proposal.get("primitive_calls") or []
        if isinstance(call, dict) and str(call.get("primitive_id") or "") in selected_ids
    ]
    if planned_calls:
        lines.insert(3, "Planned invocation bindings (resolve runtime/task placeholders, preserve "
                     "literal contract modes): " + json.dumps(
                         planned_calls, ensure_ascii=False, sort_keys=True
                     ))
    if result.proposal.get("late_bind_required") is True:
        lines.insert(3, "Late-binding invariant: this code owns only a downstream operation. "
                     "Before its first call, establish a validated upstream candidate set "
                     "with the task's ordinary scratch/site acquisition, then append a "
                     "candidate_set_ready event to primitive_execution_trace.jsonl for the "
                     "downstream primitive. Call it only with a concrete identity, stable record, "
                     "identifier, or coordinates obtained from that validated set. A category, "
                     "role, unresolved name, or generic query from the goal is not a concrete "
                     "candidate. Do not execute the primitive merely to probe candidates, and do "
                     "not let its implementation define the upstream candidate set. If the set "
                     "cannot be established, preserve the scratch solution without calling it.")
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
            "A fallback is complete only after the original frozen step succeeds in a fresh page "
            "or context, or an independent scratch acquisition covers that step's declared scope. "
            "Append fallback_completed with source_independent=true and "
            "acquisition_complete_for_scope=true only after that work actually finishes. Merely "
            "writing fallback_used, encountering one unavailable backend, or exhausting primitive "
            "aliases cannot end the task and cannot justify NOT_FOUND_ERROR; continue the frozen "
            "scratch plan until the original acceptance checks pass or complete scoped absence is "
            "independently established.",
            "Do not apply a patch when its successful output still requires the original acquisition "
            "unconditionally for missing task-required fields or completeness. In that case the "
            "primitive adds work rather than replacing work: follow the frozen scratch plan directly."
            if include_code else
            "Do not treat metadata exposure as a reason to run an extra acquisition strategy.",
            "Final projection invariant: return exactly the fields the goal asks for. Evidence used "
            "to validate, rank, or disambiguate a result is not automatically part of the answer. "
            "Do not append an unrequested count, identifier, route metric, explanation, or provenance "
            "to an otherwise exact answer; keep that support in logs/artifacts instead.",
            "Requested-fact ledger invariant: before acquisition, copy every frozen "
            "requested_output_fact into a ledger. Track each as observed, derived, absence_proven, "
            "or unresolved, together with value, value type, subject identity, source scope, and "
            "evidence. SUCCESS requires every requested fact to be non-unresolved and represented "
            "in the final projection with the requested semantic type. Check completeness before "
            "concision: never discard an acquired requested field merely to make the answer shorter. "
            "A derived fact must name its observed premises; a missing display value is unresolved, "
            "not automatically proof of absence or a substitute answer.",
            "Subject-lineage invariant: a value can satisfy a requested entity attribute only when "
            "its stable subject identity matches the accepted entity and its source scope actually "
            "owns that attribute. Page, viewport, session, container, aggregate, or current-catalog "
            "state must not be substituted for an entity-specific, record-specific, historical, or "
            "transaction-scoped value. Preserve authoritative source precision; a rounded display "
            "or global page state cannot replace a more specific acquired record value.",
            "Semantic-reducer invariant: classify free text as atomic claims with aspect, polarity, "
            "and an evidence span before filtering or aggregation. An explicit claim about one aspect "
            "must not be canceled by praise, criticism, or a rating about another aspect. Ratings are "
            "supporting evidence, not a veto over explicit text. Evaluate the whole acquired population "
            "before selecting a match; do not lock onto the first loose match. If a non-empty complete "
            "population becomes an empty answer through a preserved semantic filter, independently "
            "re-check the extracted claims before accepting the empty result.",
            "Preserved-effect invariant: a primitive may change browser URL, page state, cookies, "
            "authentication, request context, or form state even when it returns typed data. Before "
            "calling it, record the preconditions required by preserved scratch steps. After the call, "
            "verify those preconditions and re-establish them before continuing when necessary. Do not "
            "treat repeated login, redirect, or state-recovery failures as website absence.",
            "For each actually called primitive, append one JSON object per lifecycle event to "
            "primitive_execution_trace.jsonl. Use events entered, completed, acceptance_passed, "
            "acceptance_failed, fallback_used, and fallback_completed, and include primitive_id "
            "and scratch_step_id."
            if include_code else
            "Do not write primitive execution events because implementation code is withheld.",
        ]
    else:
        lines.insert(3, "For each actually called primitive, append one JSON object per lifecycle "
                     "event to primitive_execution_trace.jsonl. Use events entered, completed, "
                     "acceptance_passed, acceptance_failed, and fallback_used, and include the "
                     "primitive_id. Do not mark acceptance_passed until the returned output and, "
                     "for browser-changing methods, the live page satisfy the acceptance rules. "
                     "Use only the verified closed acquisitions. Vendor selected primitive "
                     "method bodies verbatim into standalone final_script.py; ADAPT means compose "
                     "them with task-layer code, not rewrite their selectors, endpoints, filters, "
                     "pagination, or parsers. If an exact method cannot run in the chosen runtime, "
                     "do not emulate it under the original provenance marker: fall back to the "
                     "scratch acquisition. An empty primitive result is not proof of absence unless "
                     "the relevant acquisition is accepted and complete for the task scope. For a "
                     "primitive whose semantic input is a site search/autocomplete query, query choice "
                     "and reformulation remain workflow logic: when the literal goal phrase returns "
                     "empty, unresolved, or error-marked, first retry the same primitive with a small "
                     "goal-derived family of shorter names or aliases and deduplicate typed "
                     "records by stable identity. This does not turn the query family into an exhaustive "
                     "collection or justify absence; use scratch fallback if the retried acquisition is "
                     "still empty or lacks required fields. Before issuing a search, freeze the goal's "
                     "immutable entity constraints in the task layer: the requested identity plus every "
                     "explicit entity-kind, type, category, role, parent/scope, and locality qualifier. "
                     "Record those constraints before inspecting candidates. Query reformulation may omit "
                     "terms to improve recall, but candidate acceptance must not omit or weaken any frozen "
                     "constraint. Freeze any allowed spelling, abbreviation, localization, or typed-category "
                     "aliases at the same time; do not invent a new alias after inspecting a candidate. A "
                     "parent, container, or related entity that shares only part of the requested name is not "
                     "the requested entity. Accept a candidate only when every frozen semantic facet is "
                     "explicitly supported by its canonical label, a pre-frozen alias, a typed field, stable "
                     "identity/URL, or an acquired detail-page heading. If the primitive output contract and "
                     "preserved scratch evidence expose none of those supports, "
                     "it cannot establish that entity match and the workflow must use scratch fallback. "
                     "A structurally valid "
                     "record is not task-semantic acceptance: its identity, required entity kind/type/"
                     "category or role, parent/scope, and locality constraints must remain supported by "
                     "the returned canonical name or typed fields. If no record satisfies those invariant "
                     "constraints, do not choose the first or highest-ranked record by default; record "
                     "acceptance_failed and run the scratch fallback. Mark acceptance_passed only after "
                     "both contract-level structural checks and task-semantic checks pass. For an "
                     "exhaustive request, a partial acquisition that finds no qualifying candidate "
                     "must fall back to scratch discovery rather than emit a successful empty list. "
                     "For open-ended nearest/all/vicinity requests, do not let a single query- or "
                     "page-scoped primitive define the candidate set: preserve scratch candidate "
                     "discovery unless a primitive explicitly guarantees the required scope. "
                     "Preserve the goal's cardinality: wording such as 'a', 'an', or 'the nearest' "
                     "requires at most one selected entity unless the goal explicitly asks for all. "
                     "A primitive call is not accepted merely because it returned normally. Before "
                     "accepting a browser-changing primitive, inspect both its returned success/evidence "
                     "fields and the live page. A false result-presence flag, an unresolved/error-marked "
                     "form control, or a missing expected result region means acceptance_failed even when "
                     "the URL, form values, or selected mode changed. A failed literal query may be retried "
                     "through that exact primitive using the goal-derived alias rule above; every retry "
                     "needs a fresh acceptance check. If no retry is accepted, run the scratch "
                     "acquisition/navigation and do not declare the requested navigation complete. A partial "
                     "or query-scoped primitive that does not support absence proof can never justify "
                     "NOT_FOUND_ERROR through empty results, failed aliases, or one unavailable fallback "
                     "backend. In that case run a source-independent scratch acquisition in a fresh page or "
                     "context and append fallback_completed with source_independent=true and "
                     "acquisition_complete_for_scope=true only after that acquisition actually covers the "
                     "task scope. NOT_FOUND_ERROR is allowed only after such a complete fallback; otherwise "
                     "continue scratch replanning instead of stopping early. Before "
                     "SUCCESS, check that every task-required output field is present, non-null, "
                     "non-empty, and has the declared type. If any required field fails that check, "
                     "the primitive acquisition failed: immediately run a scratch acquisition for "
                     "that fact and do not submit the failed primitive output. Before SUCCESS, "
                     "treat every router-declared remaining gap that asks for another website fact "
                     "as mandatory acquisition work. A partial answer is not SUCCESS: acquire the "
                     "missing fact with the scratch method, or return NOT_FOUND_ERROR for the whole "
                     "task when the site cannot provide it. Do not label an uncovered requested fact "
                     "as merely unavailable while submitting the fields the primitive did provide. "
                     "validate every requested output field against acquired facts. The final answer "
                     "must project exactly the fields the user requested; omit primitive evidence "
                     "fields such as endpoints, duration, distance, identity, or provenance when they "
                     "were not requested. Typed canonical fields are authoritative for comparison "
                     "and validation. For requested source quantities, preserve a site/source-aligned "
                     "explicit rendering when one is available (for example 1h44min rather than "
                     "replacing it with 104 minutes). When a site display value is compact or ambiguous "
                     "(for example H:MM), derive the answer from its typed canonical value (for "
                     "example duration_seconds) and render explicit units such as hours/minutes; "
                     "do not copy an unlabeled display value into the final answer. "
                     "Compute or report an arithmetic difference only when the current goal asks "
                     "for that difference; do not add derived fields to a source-value lookup. "
                     "When a difference is requested, include the canonical scalar in one explicit "
                     "unit (for example 92 minutes); a compound rendering such as 1 hour 32 minutes "
                     "may be added but must not replace that scalar. "
                     "A raw backend/UTC timestamp is not authoritative for a site's displayed calendar "
                     "date unless the primitive contract explicitly provides display-date or timezone "
                     "semantics. When the task asks when/on what date and the contract lacks that "
                     "semantic field, acquire the site-visible date with the scratch method rather "
                     "than formatting the raw timestamp directly. "
                     "Preserve site-returned address values verbatim (for example, do not abbreviate "
                     "a full state name). If a requested field is absent but is unambiguously "
                     "entailed by other acquired facts, derive and record it explicitly with those "
                     "premises. For example, a verified terminal lifecycle state may entail that a "
                     "requested future event will not occur; merely failing to observe the event field "
                     "does not. Otherwise use scratch "
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
        "proposal": result.proposal,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
