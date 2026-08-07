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


OPS = {"ADD", "MODIFY", "SPLIT", "ARCHIVE", "NO_CHANGE"}


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


_SYS = """Compare a new gold-admitted standalone workflow with gold workflows from OTHER
templates on the same website and the active primitive catalog. Propose only reusable website
capabilities, not task-specific filtering, aggregation, formatting, or answers.
Return JSON {"operations": [...]} using ADD, MODIFY, SPLIT, ARCHIVE, or NO_CHANGE.
For every ADD or MODIFY, put these fields directly on the operation:
`primitive_id`, `capability`, `entrypoint`, `candidate_code`, `signature`, `requires`,
`provides`, `source_templates`, `source_workflows`, and `supported_patterns`.
`primitive_id` must be exactly `<site>/<safe_snake_case_name>` (for example
`shopping/parse_product_reviews`). `signature` must be a JSON object, not a string.
`requires` and `provides` must be short machine-readable runtime-state tokens such as
`product_page_context` or `typed_review_records`, not prose descriptions or code dependencies.
`source_workflows` must copy exact workflow `id` values from the input, and
`source_templates` must contain their exact `template_id` values. Do not omit or infer provenance.
Every code candidate must define its entrypoint, include private helpers, and must not import or
call another catalog primitive. `candidate_code` must be a valid standalone Python module even
when the source workflow used JavaScript or Playwright evaluate snippets; translate reusable
behavior into Python and never emit JavaScript as the module body. ADD requires evidence from at
least two distinct task templates.
The new workflow counts toward that total: one new workflow plus one peer from a different
template is already two-template evidence and is sufficient for ADD when their code supports a
shared website capability. Do not reject merely because there is only one peer workflow.
SPLIT contains `primitive_id` for the old primitive and full candidate objects in `replacements`.
Use NO_CHANGE when there is no clear cross-template reusable unit. The catalog is not executable
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
            if "op" not in value and isinstance(value.get("operation"), str):
                value = {**value, "op": value["operation"]}
            candidate = value.get("candidate")
            if isinstance(candidate, dict):
                evidence_text = json.dumps(value.get("evidence") or [], ensure_ascii=False)
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
                    "supported_patterns": candidate.get("supported_patterns") or [],
                }
            known = {k: v for k, v in value.items()
                     if k in PrimitiveOperation.__dataclass_fields__}
            if not isinstance(known.get("op"), str) or not known["op"].strip():
                continue
            operations.append(PrimitiveOperation(**known))
    return operations


def _primitive_from_value(site: str, value: PrimitiveOperation | dict) -> Primitive:
    data = asdict(value) if isinstance(value, PrimitiveOperation) else dict(value)
    pid = data.get("primitive_id") or ""
    return Primitive(
        primitive_id=pid,
        site=site,
        capability=data.get("capability") or "",
        entrypoint=data.get("entrypoint") or pid.split("/", 1)[-1],
        code=data.get("candidate_code") or data.get("code") or "",
        signature=data.get("signature") or {},
        requires=list(data.get("requires") or []),
        provides=list(data.get("provides") or []),
        source_templates=list(data.get("source_templates") or []),
        source_workflows=list(data.get("source_workflows") or []),
        supported_patterns=list(data.get("supported_patterns") or []),
    )


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
                if len(set(primitive.source_templates)) < 2:
                    raise ValueError(f"{op} requires at least two source templates")
                if not set(primitive.source_workflows) <= gold_workflows:
                    raise ValueError("one or more source workflows are not gold-admitted")
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
                    if len(set(p.source_templates)) < 2:
                        raise ValueError("each SPLIT replacement requires two source templates")
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
