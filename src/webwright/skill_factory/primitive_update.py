"""Propose and safely apply cross-template primitive catalog changes.

The LLM proposes structured operations; it never writes the catalog directly.  Static admission
checks are intentionally modest in the MVP because primitives are prompt material, not executable
runtime dependencies.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .primitive_catalog import Primitive, PrimitiveCatalog, validate_primitive


OPS = {"ADD", "MODIFY", "NO_CHANGE"}


@dataclass
class PrimitiveOperation:
    op: str
    primitive_id: str | None = None
    capability: str = ""
    entrypoint: str = ""
    candidate_code: str = ""
    signature: dict = field(default_factory=dict)
    requires: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    source_templates: list[int | str] = field(default_factory=list)
    source_workflows: list[str] = field(default_factory=list)
    source_evidence: list[dict] = field(default_factory=list)
    evidence_verified: bool | None = None
    evidence_verification_reason: str = ""
    supported_patterns: list[str] = field(default_factory=list)
    replacements: list[dict] = field(default_factory=list)
    reason: str = ""
    confidence: float = 1.0
    contains_source_answer: bool = False


@dataclass
class UpdateResult:
    applied: list[dict] = field(default_factory=list)
    reviewed: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


_SYS = """Extract reusable site-specific synthesis primitives from a new gold-admitted standalone
workflow, then compare them with workflows from other templates and the active primitive catalog.
One real source workflow is sufficient for a new single_source primitive: a future unseen task may
be its first consumer. When an existing catalog primitive matches, use MODIFY with the union of
real provenance rather than adding a duplicate; two source templates make it shared.
Propose only reusable website operations or stable site-output parsing, not generic programming,
generic HTTP/browser setup, task-specific filtering, aggregation, formatting, or answers.
Return JSON {"operations": [...]} using ADD, MODIFY, or NO_CHANGE.
For every ADD or MODIFY, put these fields directly on the operation:
`primitive_id`, `capability`, `entrypoint`, `candidate_code`, `signature`, `requires`,
`provides`, `source_templates`, `source_workflows`, `source_evidence`, and
`supported_patterns`.
`primitive_id` must be exactly `<site>/<safe_snake_case_name>` (for example
`shopping/parse_product_reviews`). `signature` must be a JSON object, not a string.
`requires` and `provides` must be short machine-readable runtime-state tokens such as
`product_page_context` or `typed_review_records`, not prose descriptions or code dependencies.
`source_workflows` must copy exact workflow `id` values from the input, and
`source_templates` must contain their exact `template_id` values. Do not omit or infer provenance.
`source_evidence` must contain one object per cited workflow:
{"workflow_id": <exact id>, "template_id": <exact id>, "code_quote": <a contiguous verbatim
substring from that workflow's code>, "explanation": <how this exact code implements the proposed
capability>}. The quote must include the capability-specific implementation, not generic imports,
logging, browser setup, navigation, or generic page-text retrieval. Login may itself be a valid
site-specific primitive when that is the claimed capability. Never cite a workflow that lacks the
claimed implementation. Similar goals or use of the same website are not code evidence.
Every code candidate must define its entrypoint, include private helpers, and must not import or
call another catalog primitive. `candidate_code` must be a valid standalone Python module even
when the source workflow used JavaScript or Playwright evaluate snippets; translate reusable
behavior into Python and never emit JavaScript as the module body. ADD requires at least one real
source workflow. Never cite a second workflow unless its quoted code directly supports the
capability. A one-source ADD is valid and graded single_source; source count is confidence
metadata, not an admission requirement.
Use NO_CHANGE when there is no clear reusable site-specific unit. The catalog is not executable
and workflows vendor code; do not propose imports or dependency versions."""


def propose_updates(
    *,
    site: str,
    new_workflow: dict,
    peer_workflows: list[dict],
    catalog: PrimitiveCatalog,
    llm_fn: Callable[[str, str], dict] | None = None,
) -> list[PrimitiveOperation]:
    """Ask for structured proposals. Callers may inject a deterministic proposer for evaluation."""
    if llm_fn is None:
        from .llm import llm_json
        llm_fn = llm_json
    current = [{
        "primitive_id": p.primitive_id,
        "capability": p.capability,
        "entrypoint": p.entrypoint,
        "signature": p.signature,
        "requires": p.requires,
        "provides": p.provides,
        "source_templates": p.source_templates,
        "source_workflows": p.source_workflows,
        "source_evidence": p.source_evidence,
        "grade": p.grade,
        "supported_patterns": p.supported_patterns,
        "code": p.code,
    } for p in catalog.list()]
    user = json.dumps({
        "site": site,
        "new_workflow": new_workflow,
        "peer_workflows": peer_workflows,
        "active_catalog": current,
    }, ensure_ascii=False)
    raw = llm_fn(_SYS, user) or {}
    known_workflows = [new_workflow, *peer_workflows]
    raw_operations = raw.get("operations")
    if not isinstance(raw_operations, list) and isinstance(raw.get("candidate"), dict):
        candidate = dict(raw["candidate"])
        candidate.setdefault("name", raw.get("name"))
        candidate.setdefault("summary", raw.get("description"))
        raw_operations = [{
            "op": "ADD",
            "candidate": candidate,
            "evidence": raw.get("sources") or [],
        }]
    operations = []
    for value in raw_operations or []:
        if isinstance(value, dict):
            if "op" not in value:
                alias = next(
                    (value.get(key) for key in ("operation", "action", "type")
                     if isinstance(value.get(key), str)),
                    None,
                )
                if alias:
                    value = {**value, "op": alias}
            candidate = value.get("candidate")
            if isinstance(candidate, dict):
                legacy_evidence = value.get("evidence") or []
                evidence_text = json.dumps(legacy_evidence, ensure_ascii=False)
                cited = [
                    workflow for workflow in known_workflows
                    if str(workflow.get("id") or "") in evidence_text
                ]
                name = candidate.get("name") or candidate.get("entrypoint") or ""
                value = {
                    **value,
                    "primitive_id": candidate.get("primitive_id") or (
                        f"{site}/{name}" if name else None
                    ),
                    "capability": candidate.get("capability")
                    or candidate.get("summary") or "",
                    "entrypoint": candidate.get("entrypoint") or name,
                    "candidate_code": candidate.get("candidate_code")
                    or candidate.get("code") or "",
                    "signature": candidate.get("signature") or {},
                    "requires": candidate.get("requires") or [],
                    "provides": candidate.get("provides") or [],
                    "source_templates": candidate.get("source_templates") or [
                        workflow.get("template_id") for workflow in cited
                    ],
                    "source_workflows": candidate.get("source_workflows") or [
                        workflow.get("id") for workflow in cited
                    ],
                    "source_evidence": candidate.get("source_evidence")
                    or value.get("source_evidence") or (
                        legacy_evidence
                        if legacy_evidence and all(isinstance(x, dict) for x in legacy_evidence)
                        else []
                    ),
                    "supported_patterns": candidate.get("supported_patterns") or [],
                }
            known = {k: v for k, v in value.items()
                     if k in PrimitiveOperation.__dataclass_fields__}
            if not isinstance(known.get("op"), str) or not known["op"].strip():
                continue
            operations.append(PrimitiveOperation(**known))
    # MODIFY unions evidence: prior verified provenance must survive a later observation.
    for operation in operations:
        if operation.op.upper() != "MODIFY" or not operation.primitive_id:
            continue
        existing = catalog.get(operation.primitive_id)
        if existing is None:
            continue
        operation.source_templates = list(dict.fromkeys([
            *existing.source_templates, *operation.source_templates,
        ]))
        operation.source_workflows = list(dict.fromkeys([
            *existing.source_workflows, *operation.source_workflows,
        ]))
        evidence = {
            str(row.get("workflow_id")): row
            for row in [*existing.source_evidence, *operation.source_evidence]
            if isinstance(row, dict) and row.get("workflow_id")
        }
        operation.source_evidence = list(evidence.values())
    return operations


def _primitive_from_value(site: str, value: PrimitiveOperation | dict) -> Primitive:
    data = asdict(value) if isinstance(value, PrimitiveOperation) else dict(value)
    pid = data.get("primitive_id") or ""
    source_templates = list(data.get("source_templates") or [])
    return Primitive(
        primitive_id=pid,
        site=site,
        capability=data.get("capability") or "",
        entrypoint=data.get("entrypoint") or pid.split("/", 1)[-1],
        code=data.get("candidate_code") or data.get("code") or "",
        signature=data.get("signature") or {},
        requires=list(data.get("requires") or []),
        provides=list(data.get("provides") or []),
        source_templates=source_templates,
        source_workflows=list(data.get("source_workflows") or []),
        source_evidence=list(data.get("source_evidence") or []),
        evidence_verified=data.get("evidence_verified"),
        evidence_verification_reason=data.get("evidence_verification_reason") or "",
        grade="shared" if len({str(x) for x in source_templates}) >= 2 else "single_source",
        supported_patterns=list(data.get("supported_patterns") or []),
    )


def _normalize_code(text: str) -> str:
    return " ".join((text or "").split())


def validate_source_evidence(operation, workflow_evidence: dict[str, dict]) -> None:
    """Require a real, sufficiently specific code span from every cited workflow."""
    evidence = operation.source_evidence or []
    by_id = {
        row.get("workflow_id"): row for row in evidence
        if isinstance(row, dict) and row.get("workflow_id")
    }
    cited = set(operation.source_workflows)
    if set(by_id) != cited:
        raise ValueError("source_evidence must cover exactly every source workflow")
    templates = set()
    for workflow_id in operation.source_workflows:
        workflow = workflow_evidence.get(workflow_id)
        if workflow is None:
            raise ValueError(f"missing workflow evidence source {workflow_id}")
        row = by_id[workflow_id]
        if str(row.get("template_id")) != str(workflow.get("template_id")):
            raise ValueError(f"source evidence template mismatch for {workflow_id}")
        quote = _normalize_code(str(row.get("code_quote") or ""))
        code = _normalize_code(str(workflow.get("code") or ""))
        if len(quote) < 80:
            raise ValueError(f"source evidence quote too short for {workflow_id}")
        if quote not in code:
            raise ValueError(f"source evidence quote not found in {workflow_id}")
        if len(str(row.get("explanation") or "").strip()) < 20:
            raise ValueError(f"source evidence explanation too short for {workflow_id}")
        templates.add(str(workflow.get("template_id")))
    if not templates:
        raise ValueError("verified source evidence requires at least one template")


_EVIDENCE_JUDGE_SYS = """You are an independent code-evidence gate for reusable web primitives.
For every proposed operation and every cited workflow quote, decide whether the quote DIRECTLY
performs the same stable website operation from which the proposed generalized candidate can be
synthesized. The source snippets need not have identical wrappers or final return shapes: local
top-result selection, normalization, aggregation, and output formatting may differ. However, each
quote must itself execute the capability-specific site operation; same website, login, navigation,
generic HTTP setup, generic page-text access, or a related task goal are not sufficient. Check that
the candidate signature and code do not claim a site operation absent from any cited source. One
workflow is sufficient when its quote directly implements a reusable site-specific capability;
do not reject it merely because there is no second source. Return
strict JSON:
{"verdicts":[{"primitive_id":"...","supported_workflows":["..."],
"redundant_with":null|"<active-or-proposed-primitive-id>","reason":"..."}]}.
Compare against the active catalog and other proposals. If an existing primitive already covers
the capability, or the proposal is merely a narrower/wider wrapper around it, set redundant_with;
the updater should MODIFY the existing primitive or return NO_CHANGE instead of ADD.
Do not repair proposals and do not infer behavior absent from the quoted code."""


def verify_operations_evidence(
    operations, workflow_evidence, *, active_primitives=None, llm_fn=None
):
    """Statically locate evidence, then independently judge semantic support."""
    if llm_fn is None:
        from .llm import llm_json
        llm_fn = llm_json
    candidates = []
    for operation in operations:
        if operation.op.upper() not in {"ADD", "MODIFY"}:
            continue
        try:
            validate_source_evidence(operation, workflow_evidence)
        except ValueError as exc:
            operation.evidence_verified = False
            operation.evidence_verification_reason = str(exc)
            continue
        candidates.append({
            "primitive_id": operation.primitive_id,
            "capability": operation.capability,
            "signature": operation.signature,
            "candidate_code": operation.candidate_code,
            "source_evidence": operation.source_evidence,
        })
    if not candidates:
        return operations
    raw = llm_fn(
        _EVIDENCE_JUDGE_SYS,
        json.dumps({
            "operations": candidates,
            "active_catalog": [
                {
                    "primitive_id": primitive.primitive_id,
                    "capability": primitive.capability,
                    "signature": primitive.signature,
                    "supported_patterns": primitive.supported_patterns,
                }
                for primitive in (active_primitives or [])
            ],
        }, ensure_ascii=False),
    ) or {}
    verdicts = {
        row.get("primitive_id"): row for row in raw.get("verdicts") or []
        if isinstance(row, dict) and row.get("primitive_id")
    }
    for operation in operations:
        if operation.op.upper() not in {"ADD", "MODIFY"} or operation.evidence_verified is False:
            continue
        verdict = verdicts.get(operation.primitive_id, {})
        supported = set(verdict.get("supported_workflows") or [])
        required = set(operation.source_workflows)
        redundant_with = verdict.get("redundant_with")
        operation.evidence_verified = supported == required and not redundant_with
        operation.evidence_verification_reason = str(
            (
                f"capability is redundant with {redundant_with}: "
                if redundant_with else ""
            )
            + (verdict.get("reason") or "independent evidence judge returned no complete verdict")
        )
    return operations


def _record_review(path: str | Path | None, row: dict) -> None:
    if path is None:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def apply_updates(
    catalog: PrimitiveCatalog,
    operations: list[PrimitiveOperation],
    *,
    gold_workflows: set[str],
    workflow_evidence: dict[str, dict] | None = None,
    review_path: str | Path | None = None,
    confidence_threshold: float = 0.7,
) -> UpdateResult:
    """Apply admitted proposals and retain uncertain/invalid proposals as review evidence."""
    result = UpdateResult()
    for operation in operations:
        row = asdict(operation)
        op = operation.op.upper()
        row["op"] = op
        if op not in OPS:
            row["error"] = f"unknown operation {op!r}"
            result.rejected.append(row)
            continue
        if op == "NO_CHANGE":
            result.applied.append({"op": op, "reason": operation.reason})
            continue
        if operation.confidence < confidence_threshold:
            row["review_reason"] = "proposal confidence below automatic threshold"
            result.reviewed.append(row)
            _record_review(review_path, row)
            continue
        if operation.contains_source_answer:
            row["review_reason"] = "candidate may hardcode a source task answer"
            result.reviewed.append(row)
            _record_review(review_path, row)
            continue

        try:
            if op in {"ADD", "MODIFY"}:
                primitive = _primitive_from_value(catalog.site, operation)
                if op == "ADD" and catalog.get(primitive.primitive_id):
                    raise ValueError("ADD target already exists")
                if op == "MODIFY" and not catalog.get(primitive.primitive_id):
                    raise ValueError("MODIFY target does not exist")
                if not primitive.source_templates or not primitive.source_workflows:
                    raise ValueError(f"{op} requires at least one source workflow and template")
                if not set(primitive.source_workflows) <= gold_workflows:
                    raise ValueError("one or more source workflows are not gold-admitted")
                if workflow_evidence is not None:
                    validate_source_evidence(operation, workflow_evidence)
                    if operation.evidence_verified is not True:
                        raise ValueError(
                            "independent evidence verification failed: "
                            + (operation.evidence_verification_reason or "no verdict")
                        )
                catalog.upsert(primitive)
                result.applied.append({
                    "op": op, "primitive_id": primitive.primitive_id,
                    "content_hash": primitive.content_hash,
                })
            elif op == "ARCHIVE":
                if not operation.primitive_id or not catalog.archive(operation.primitive_id):
                    raise ValueError("ARCHIVE target does not exist")
                result.applied.append({"op": op, "primitive_id": operation.primitive_id})
            elif op == "SPLIT":
                if not operation.primitive_id or not catalog.get(operation.primitive_id):
                    raise ValueError("SPLIT target does not exist")
                if len(operation.replacements) < 2:
                    raise ValueError("SPLIT needs at least two replacement primitives")
                replacements = [_primitive_from_value(catalog.site, x)
                                for x in operation.replacements]
                existing_entrypoints = {p.entrypoint for p in catalog.list()
                                        if p.primitive_id != operation.primitive_id}
                replacement_entrypoints = {p.entrypoint for p in replacements}
                if len(replacement_entrypoints) != len(replacements):
                    raise ValueError("SPLIT replacement entrypoints must be unique")
                for p in replacements:
                    if not p.source_templates or not p.source_workflows:
                        raise ValueError(
                            "each SPLIT replacement requires at least one source workflow"
                        )
                    if not set(p.source_workflows) <= gold_workflows:
                        raise ValueError("one or more source workflows are not gold-admitted")
                    validate_primitive(
                        p, other_entrypoints=existing_entrypoints | replacement_entrypoints
                    )
                for p in replacements:
                    catalog.upsert(p)
                catalog.archive(operation.primitive_id)
                result.applied.append({
                    "op": op, "primitive_id": operation.primitive_id,
                    "replacements": [p.primitive_id for p in replacements],
                })
        except (ValueError, OSError) as exc:
            row["error"] = str(exc)
            result.rejected.append(row)
    return result
