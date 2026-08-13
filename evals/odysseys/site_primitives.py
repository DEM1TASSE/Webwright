"""Site-level primitive routing for multi-site Odysseys tasks.

Odysseys tasks are task-level records, while audited primitive libraries are site-level.
This module keeps that boundary explicit: a reviewed segment manifest supplies one subgoal
per site visit, and each subgoal is independently planned, gated, and retrieved.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class SiteSubgoal:
    segment_id: str
    site: str | None
    goal: str
    template_id: str = ""
    rubric_ids: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()


@dataclass
class SegmentRetrieval:
    segment: SiteSubgoal
    decision: str = "skip"
    reason: str = ""
    primitive_sources: list[dict] = field(default_factory=list)
    hint: str = ""
    scratch_plan: dict | None = None
    record_path: str | None = None


def canonical_site(value: str) -> str:
    """Convert a URL/host/library slug to the slug used by audited libraries."""
    raw = str(value or "").strip().lower()
    if not raw:
        raise ValueError("site cannot be empty")
    parsed = urlparse(raw if "://" in raw else "//" + raw)
    host = parsed.hostname or raw
    if host.startswith("www."):
        host = host[4:]
    # Google products share a registrable domain but not an interaction surface.  Keep Maps
    # separate from generic Google Search so its routes/actions can never leak across libraries.
    if host == "maps.google.com" or (
        host == "google.com" and (parsed.path == "/maps" or parsed.path.startswith("/maps/"))
    ):
        return "google_maps"
    slug = re.sub(r"[^a-z0-9]+", "_", host).strip("_")
    if not slug or not slug[0].isalpha():
        raise ValueError(f"cannot canonicalize site: {value!r}")
    return slug


def load_segments(path: str | Path, task_id: str) -> list[SiteSubgoal]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("tasks", raw) if isinstance(raw, dict) else raw
    if isinstance(rows, dict):
        rows = rows.get(task_id, [])
    elif isinstance(rows, list) and rows and "task_id" in rows[0]:
        match = next((row for row in rows if str(row.get("task_id")) == task_id), None)
        rows = (match or {}).get("segments", [])
    if not isinstance(rows, list):
        raise ValueError(f"no segment list for task {task_id}")
    segments = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"segment {index} must be an object")
        site = row.get("site")
        segments.append(SiteSubgoal(
            segment_id=str(row.get("segment_id") or f"S{index}"),
            site=canonical_site(site) if site else None,
            goal=str(row.get("goal") or "").strip(),
            template_id=str(row.get("template_id") or "").strip(),
            rubric_ids=tuple(str(x) for x in row.get("rubric_ids") or []),
            required_fields=tuple(str(x) for x in row.get("required_fields") or []),
        ))
    validate_segments(segments)
    return segments


def validate_segments(segments: list[SiteSubgoal]) -> None:
    if not segments:
        raise ValueError("at least one segment is required")
    ids, rubrics = set(), set()
    for segment in segments:
        if not segment.segment_id or segment.segment_id in ids:
            raise ValueError(f"duplicate/empty segment_id: {segment.segment_id!r}")
        ids.add(segment.segment_id)
        if not segment.goal:
            raise ValueError(f"segment {segment.segment_id} has no goal")
        overlap = rubrics.intersection(segment.rubric_ids)
        if overlap:
            raise ValueError(f"rubrics assigned to multiple segments: {sorted(overlap)}")
        rubrics.update(segment.rubric_ids)


def route_site_segments(
    segments: list[SiteSubgoal], library: str | Path, records_dir: str | Path, *,
    plan_fn=None, decide_fn=None, include_code: bool = True,
) -> list[SegmentRetrieval]:
    """Independently route every site segment; answer-only segments never see a library."""
    from webwright.skill_factory.audited_primitive_retrieve import (
        draft_scratch_plan, render_audited_primitive_hint,
        retrieve_audited_primitives, write_audited_retrieval,
    )

    output = []
    records = Path(records_dir)
    records.mkdir(parents=True, exist_ok=True)
    for segment in segments:
        if segment.site is None:
            output.append(SegmentRetrieval(
                segment=segment, reason="answer-only segment; no site primitive retrieval",
            ))
            continue
        plan = draft_scratch_plan(segment.goal, site=segment.site, plan_fn=plan_fn)
        index = Path(library) / segment.site / "final_candidate" / "index.json"
        if not index.is_file():
            output.append(SegmentRetrieval(
                segment=segment, reason=f"no audited library for {segment.site}",
                scratch_plan=plan,
            ))
            continue
        retrieval = retrieve_audited_primitives(
            segment.goal, library, site=segment.site, scratch_plan=plan,
            decide_fn=decide_fn,
        )
        record = records / f"{segment.segment_id}.{segment.site}.primitive_retrieval.json"
        write_audited_retrieval(record, retrieval, task=segment.goal)
        output.append(SegmentRetrieval(
            segment=segment, decision=retrieval.decision, reason=retrieval.reason,
            primitive_sources=retrieval.sources,
            hint=render_audited_primitive_hint(retrieval, include_code=include_code),
            scratch_plan=plan, record_path=str(record),
        ))
    return output


def render_multisite_hint(results: list[SegmentRetrieval]) -> str:
    """Render only approved local patches without changing the task on a skip.

    The full Odysseys instruction remains the completion target.  A segment is routing
    metadata, not a smaller replacement task, so skipped segments must be prompt-neutral.
    """
    adapted = [result for result in results
               if result.decision == "adapt" and result.hint.strip()]
    if not adapted:
        return ""
    sections = [
        "## Optional local implementation patches for the full Odysseys task",
        "The original task after this block is the sole completion target. Complete every "
        "requirement in it, including all sites, aggregation, end-state tabs, and final output. "
        "Each patch below applies only while executing its named site sub-operation; it is not "
        "a replacement task and is never a reason to stop after that sub-operation. Preserve "
        "all unrelated scratch work and do not transfer selectors, facts, or assumptions "
        "between sites. Segments whose gate skipped retrieval are intentionally omitted so "
        "their execution remains identical to scratch.",
    ]
    for result in adapted:
        segment = result.segment
        sections.extend([
            "",
            f"### Local patch {segment.segment_id}: {segment.site}",
            f"Sub-operation only: {segment.goal}",
            f"Approved gate: adapt ({result.reason})",
        ])
        sections.append(result.hint.rstrip())
    return "\n".join(sections).rstrip() + "\n"


def write_routing_manifest(path: str | Path, task_id: str,
                           results: list[SegmentRetrieval]) -> None:
    payload = {
        "task_id": task_id,
        "routing_scope": "site_segment",
        "segments": [
            {
                "segment": asdict(item.segment),
                "decision": item.decision,
                "reason": item.reason,
                "primitive_sources": item.primitive_sources,
                "record_path": item.record_path,
            }
            for item in results
        ],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
