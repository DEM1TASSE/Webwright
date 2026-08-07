"""Retrieve site-scoped primitive snippets as synthesis material.

The returned snippets are copied/adapted into a standalone workflow.  ``requires`` and
``provides`` describe browser state and are used only to order/select snippets; they never
create Python imports or runtime dependencies.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .primitive_catalog import Primitive, PrimitiveCatalog


_WORD = re.compile(r"[a-z0-9_]+")
_MARKER = re.compile(r"#\s*primitive-source:\s*(\S+)\s+(sha256:[0-9a-f]{64})")


@dataclass
class PrimitiveRetrieval:
    site: str
    primitive_ids: list[str] = field(default_factory=list)
    primitives: list[Primitive] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def sources(self) -> list[dict[str, str]]:
        return [
            {"primitive_id": p.primitive_id, "content_hash": p.content_hash}
            for p in self.primitives
        ]


@dataclass
class PrimitiveRouteDecision:
    decision: str
    primitive_ids: list[str] = field(default_factory=list)
    reason: str = ""
    remaining_gap: list[str] = field(default_factory=list)


def decide_primitive_metadata(
    task: str,
    library: str | Path,
    *,
    site: str,
    decide_fn: Callable[[str, list[dict]], dict] | None = None,
) -> PrimitiveRouteDecision:
    """Choose use/adapt/skip from metadata only; no candidate code enters the judge prompt."""
    candidates = PrimitiveCatalog(library, site).list()
    metadata = [{
        "primitive_id": p.primitive_id,
        "capability": p.capability,
        "signature": p.signature,
        "requires": p.requires,
        "provides": p.provides,
        "supported_patterns": p.supported_patterns,
    } for p in candidates]
    if not metadata:
        return PrimitiveRouteDecision("skip", reason="site primitive catalog is empty")
    if decide_fn is None:
        from .llm import llm_json

        def decide_fn(current_task, values):
            return llm_json(
                "Route using primitive METADATA only. Return JSON "
                "{\"decision\":\"use|adapt|skip\",\"primitive_ids\":[],\"reason\":\"...\","
                "\"remaining_gap\":[]}. USE only when a contract directly supplies the core "
                "website facts. ADAPT when it covers a meaningful part with explicit remaining "
                "gaps. SKIP when acquiring its prerequisites is itself the main unresolved work, "
                "its output is unnecessary, or coverage is marginal. An empty selection is valid. "
                "You have not seen candidate code and must not assume capabilities absent from "
                "metadata.",
                json.dumps({"task": current_task, "candidates": values}, ensure_ascii=False),
            )
    raw = decide_fn(task, metadata) or {}
    decision = str(raw.get("decision") or "skip").lower()
    if decision not in {"use", "adapt", "skip"}:
        decision = "skip"
    allowed = {x["primitive_id"] for x in metadata}
    ids = []
    for primitive_id in raw.get("primitive_ids") or []:
        if primitive_id in allowed and primitive_id not in ids:
            ids.append(primitive_id)
    if decision in {"use", "adapt"} and not ids:
        decision = "skip"
    if decision == "skip":
        ids = []
    gaps = raw.get("remaining_gap") or []
    return PrimitiveRouteDecision(
        decision=decision,
        primitive_ids=ids,
        reason=str(raw.get("reason") or ""),
        remaining_gap=[str(x) for x in gaps if isinstance(x, str)],
    )


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2}


def _keyword_rank(task: str, primitives: list[Primitive]) -> list[str]:
    query = _terms(task)
    scored = []
    for p in primitives:
        haystack = " ".join([
            p.name, p.capability, *p.supported_patterns,
            json.dumps(p.signature, sort_keys=True),
        ])
        overlap = len(query & _terms(haystack))
        if overlap:
            scored.append((overlap, p.primitive_id))
    return [pid for _, pid in sorted(scored, key=lambda row: (-row[0], row[1]))]


def _llm_rank(task: str, primitives: list[Primitive]) -> list[str]:
    from .llm import llm_json

    candidates = [{
        "primitive_id": p.primitive_id,
        "capability": p.capability,
        "signature": p.signature,
        "requires": p.requires,
        "provides": p.provides,
        "supported_patterns": p.supported_patterns,
    } for p in primitives]
    out = llm_json(
        "Select only site primitives that materially help solve the task. "
        "Return JSON {\"primitive_ids\": [...], \"reason\": \"...\"}. "
        "Do not select merely because the website matches.",
        f"Task:\n{task}\n\nCandidates:\n{json.dumps(candidates, ensure_ascii=False)}",
    )
    ids = out.get("primitive_ids") or []
    return [str(x) for x in ids]


def _resolve_state_order(
    selected_ids: list[str],
    by_id: dict[str, Primitive],
    *,
    initial_states: set[str],
    max_primitives: int,
) -> tuple[list[Primitive], list[str]]:
    """Add available state providers and topologically order by browser-state flow."""
    wanted = [by_id[x] for x in selected_ids if x in by_id]
    wanted_ids = {p.primitive_id for p in wanted}
    available = set(initial_states)

    # Add one provider for an unmet browser-state requirement when space permits.
    changed = True
    while changed and len(wanted) < max_primitives:
        changed = False
        required = {r for p in wanted for r in p.requires} - available
        provided = {state for p in wanted for state in p.provides}
        for state in sorted(required - provided):
            provider = next(
                (p for p in by_id.values()
                 if p.primitive_id not in wanted_ids and state in p.provides),
                None,
            )
            if provider is not None:
                wanted.append(provider)
                wanted_ids.add(provider.primitive_id)
                changed = True
                break

    # Stable state-aware ordering. A snippet can run when all its state requirements exist.
    pending = list(wanted)
    ordered: list[Primitive] = []
    while pending:
        ready = [p for p in pending if set(p.requires) <= available]
        if not ready:
            # Preserve retrieval order for unresolved/cyclic metadata and report the gap.
            ordered.extend(pending)
            break
        for p in ready:
            ordered.append(p)
            available.update(p.provides)
            pending.remove(p)
    missing = sorted({r for p in ordered for r in p.requires} - available)
    # Recompute sequentially: a state provided after its consumer is still missing at that point.
    available = set(initial_states)
    missing_at_use = set()
    for p in ordered:
        missing_at_use.update(set(p.requires) - available)
        available.update(p.provides)
    return ordered[:max_primitives], sorted(missing_at_use)


def retrieve_primitives(
    task: str,
    library: str | Path,
    *,
    site: str,
    max_primitives: int = 5,
    initial_states: set[str] | None = None,
    rank_fn: Callable[[str, list[Primitive]], list[str]] | None = None,
    use_llm: bool = False,
) -> PrimitiveRetrieval:
    """Retrieve and state-order at most ``max_primitives`` from one site's active catalog."""
    if max_primitives < 1:
        return PrimitiveRetrieval(site=site, reason="primitive retrieval disabled by zero budget")
    candidates = PrimitiveCatalog(library, site).list()
    if not candidates:
        return PrimitiveRetrieval(site=site, reason="site primitive catalog is empty")
    ranker = rank_fn or (_llm_rank if use_llm else _keyword_rank)
    allowed = {p.primitive_id: p for p in candidates}
    ranked = []
    for pid in ranker(task, candidates):
        if pid in allowed and pid not in ranked:
            ranked.append(pid)
    if not ranked:
        return PrimitiveRetrieval(site=site, reason="no relevant site primitive")
    ordered, missing = _resolve_state_order(
        ranked[:max_primitives], allowed,
        initial_states=set(initial_states or ()),
        max_primitives=max_primitives,
    )
    return PrimitiveRetrieval(
        site=site,
        primitive_ids=[p.primitive_id for p in ordered],
        primitives=ordered,
        missing_requirements=missing,
        reason="retrieved site primitives",
    )


def render_primitive_hint(result: PrimitiveRetrieval) -> str:
    """Render full snippets and provenance markers for prompt-time vendoring."""
    if not result.primitives:
        return ""
    lines = [
        "## Site primitive catalog (synthesis material)",
        "Use only the useful parts. Copy/adapt them into the final standalone workflow.",
        "Do NOT import the primitive catalog or create a runtime dependency on it.",
        "Keep a `# primitive-source: <id> <hash>` comment for every snippet actually reused.",
        "At completion, also write `$WORKSPACE_DIR/primitive_usage.json` as "
        "{\"used\": [{\"primitive_id\": \"...\", \"content_hash\": \"...\"}], "
        "\"coverage_assessment\": {\"covered\": [\"...\"], \"remaining\": [\"...\"], "
        "\"sufficiency\": \"full|partial|none\"}}; use an empty `used` list if no supplied "
        "snippet was actually reused.",
    ]
    if result.missing_requirements:
        lines.append(
            "Unresolved browser-state prerequisites: "
            + ", ".join(result.missing_requirements)
            + ". Establish these explicitly in the final workflow."
        )
    for p in result.primitives:
        lines.extend([
            "",
            f"### {p.primitive_id}",
            f"capability: {p.capability}",
            f"signature: {json.dumps(p.signature, ensure_ascii=False)}",
            f"requires: {json.dumps(p.requires)}; provides: {json.dumps(p.provides)}",
            f"# primitive-source: {p.primitive_id} {p.content_hash}",
            "```python",
            p.code.rstrip(),
            "```",
        ])
    return "\n".join(lines) + "\n"


def extract_primitive_usage(code: str) -> list[dict[str, str]]:
    """Extract deduplicated provenance markers preserved in a generated standalone workflow."""
    seen = set()
    out = []
    for primitive_id, content_hash in _MARKER.findall(code):
        key = (primitive_id, content_hash)
        if key not in seen:
            seen.add(key)
            out.append({"primitive_id": primitive_id, "content_hash": content_hash})
    return out


def read_declared_usage(path: str | Path) -> list[dict[str, str]]:
    """Read the agent's declaration defensively; declaration is evidence, not proof of use."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for item in value.get("used") or []:
        if (isinstance(item, dict) and isinstance(item.get("primitive_id"), str)
                and isinstance(item.get("content_hash"), str)):
            out.append({
                "primitive_id": item["primitive_id"],
                "content_hash": item["content_hash"],
            })
    return out


def read_declared_coverage(path: str | Path) -> dict[str, object] | None:
    """Read the agent's contract-coverage assessment defensively."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    raw = value.get("coverage_assessment")
    if not isinstance(raw, dict):
        return None
    covered = raw.get("covered")
    remaining = raw.get("remaining")
    sufficiency = raw.get("sufficiency")
    if (
        not isinstance(covered, list)
        or not all(isinstance(x, str) for x in covered)
        or not isinstance(remaining, list)
        or not all(isinstance(x, str) for x in remaining)
        or sufficiency not in {"full", "partial", "none"}
    ):
        return None
    return {
        "covered": covered,
        "remaining": remaining,
        "sufficiency": sufficiency,
    }


def write_retrieval_record(path: str | Path, result: PrimitiveRetrieval, *, task: str) -> None:
    """Persist what was offered to the agent; actual use is separately inferred from markers."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "task": task,
        "site": result.site,
        "retrieved": result.sources,
        "missing_requirements": result.missing_requirements,
        "reason": result.reason,
    }
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
