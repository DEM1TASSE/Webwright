"""Admission gate: only "correct" solves/skills enter the library, preventing correct-but-narrow /
regression pollution. The gate is an INDEPENDENT second eye — distinct from the solving agent's own
self_reflection (which is a solve-completion condition, not an admission check).

Stable interface (swappable implementation), configurable method:
    gate(result, *, gold=None, output_schema=None, method="auto", status="") -> GateResult

- method="gold"        : compare against gold (benchmarks like WebArena; truly independent, catches
                         mis-extracted solves). Recommended.
- method="self_verify" : invariants (result non-empty + shape matches output_schema) plus the
                         agent's OWN final report: a run whose agent_response.json says anything
                         but SUCCESS (e.g. NOT_FOUND_ERROR) is rejected — the agent itself did not
                         believe the answer. Costs nothing; no extra model call.
                         Limitation: still self-grading — a wrong answer the agent BELIEVED is
                         admitted anyway.
                         (Note: webwright's self_reflection is always predicted_label==1 due to
                         require_self_reflection_success, so it cannot serve as the gate — that is a
                         solve-completion condition, not independent admission.)
- method="none"        : no gate (demo reuse only, no pollution protection).
- method="auto"        : use gold if available, else self_verify.
Upgrade path (next step): for real websites use WebJudge (OM2W's official judge) or cross-source
consistency checks for a truly independent gate.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GateResult:
    admit: bool
    reason: str


def load_external_verdicts(path: str | Path) -> dict[str, GateResult]:
    """Load task-level verdicts emitted by the OM2W adapter (JSONL or JSON).

    Fail closed: malformed labels and duplicate task ids are configuration errors, while a
    missing task is handled by ``external_gate`` as a rejection.
    """
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        records = payload if isinstance(payload, list) else [payload]

    verdicts: dict[str, GateResult] = {}
    for record in records:
        if not isinstance(record, dict) or not record.get("task_id"):
            raise ValueError(f"external gate record has no task_id: {record!r}")
        task_id = str(record["task_id"])
        if task_id in verdicts:
            raise ValueError(f"duplicate external gate verdict for task_id={task_id!r}")
        label = record.get("predicted_label")
        if label not in (0, 1, False, True):
            raise ValueError(f"external gate verdict for {task_id!r} has invalid predicted_label={label!r}")
        details = record.get("evaluation_details") or {}
        response = details.get("response") if isinstance(details, dict) else ""
        verdicts[task_id] = GateResult(bool(label), str(response or f"external predicted_label={int(label)}"))
    return verdicts


def external_gate(task_id: str, verdicts: dict[str, GateResult]) -> GateResult:
    """Return an imported independent verdict; missing tasks are rejected, never admitted."""
    return verdicts.get(str(task_id), GateResult(False, "no external gate verdict for task"))


def _shape_ok(result, output_schema) -> bool:
    if not output_schema:
        return True
    t = output_schema.get("type")
    if t == "array":
        return isinstance(result, list)
    if t == "object":
        return isinstance(result, dict)
    if t in ("string",):
        return isinstance(result, str)
    if t in ("number", "integer"):
        return isinstance(result, (int, float)) and not isinstance(result, bool)
    return True


def _self_verify(result, output_schema, status="") -> GateResult:
    if status and status != "SUCCESS":
        return GateResult(False, f"agent itself reported {status}")
    if result is None:
        return GateResult(False, "result is null")
    if isinstance(result, (list, dict, str)) and len(result) == 0:
        return GateResult(False, "result is empty")
    if not _shape_ok(result, output_schema):
        return GateResult(False, f"shape != output_schema ({output_schema.get('type')})")
    return GateResult(True, "self-verify passed (non-empty, shape ok)")


def _gold(result, gold) -> GateResult:
    if result == gold:
        return GateResult(True, "matches gold")
    return GateResult(False, "differs from gold")


def gate(result, *, gold=None, output_schema=None, method: str = "auto",
         status: str = "") -> GateResult:
    if method == "none":
        return GateResult(True, "no gate (admit all)")
    if method == "gold" or (method == "auto" and gold is not None):
        return _gold(result, gold)
    return _self_verify(result, output_schema, status=status)
