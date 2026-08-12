"""Audited two-phase builder for website primitive packages.

Phase 1 incrementally proposes ADD/UPDATE/SKIP into an unclassified primitive pool. Phase 2
performs one KEEP/MERGE/SPLIT pass and assigns feature classes. All LLM output is retained;
the deterministic manager validates and renders candidates but never invents primitive code.
"""
from __future__ import annotations

import ast
import hashlib
import json
import random
import re
from copy import deepcopy
from pathlib import Path
from typing import Callable

from .site_package_candidate import expected_class_name


_SAFE = re.compile(r"^[a-z][a-z0-9_]*$")

_EXTRACT_SYS = r"""Inspect exactly one gold-admitted website workflow before any cross-workflow
deduplication. Return JSON with either:
{"decision":"CANDIDATES","candidates":[{"candidate_id":"<workflow-id>::<snake-name>",
 "proposed_method":"snake_case","capability":"reusable website capability",
 "owns":[...],"does_not_own":[...],"input_contract":{...},"output_contract":{...},
 "source_evidence":{"workflow_id":"exact id","template_id":"exact id",
 "code_quote":"representative source excerpt or concise source description",
 "explanation":"what was generalized from the workflow and why it supports this capability"}}]}
or {"decision":"SKIP","candidates":[],"skip_category":"BLOCKED|NON_WEBSITE|NO_REUSABLE_SITE_CAPABILITY",
"reason":"specific reason"}.

Coverage rule: enumerate every distinct reusable site operation actually demonstrated by the
workflow. One workflow is sufficient evidence. UI/DOM/page-text acquisition IS valid when the
candidate itself parses it into typed records; returning raw page text/DOM to a workflow is not.
Site selectors, URL patterns, endpoint shapes, authentication, pagination, and stable displayed
semantics belong in primitives. Task filtering, aggregation, ranking, subjective classification,
and answer formatting stay in workflows. Local git/filesystem operations are not website
primitives. A failed/blocked attempted mutation does not prove that mutation capability.

Do not overfit a typed record to only the fields consumed by the current task. At the same
demonstrated acquisition boundary, preserve stable objective identity, temporal, state, value,
link, and pagination/completeness fields that the evidence actually exposes. This is not license
to invent undocumented fields. In particular, do not collapse contributor identity to display
name, issue records to title/href, commit timestamps to one ambiguous date field, or paginated
search results to an apparently complete list when richer facts/completeness are demonstrated.
Reserve the input name `page` for the component's browser object (`self.page`). Describe numeric
pagination inputs as `page_number` in candidate input contracts.

Do not compare against a library, merge candidates, generate code, or discard a real capability
merely because an API/embedded JSON source would be more stable. Source evidence is attribution,
not a demand to copy code verbatim: explicitly describe parameterization of hard-coded instance
values and removal of task-specific logic."""

_BUILD_SYS = r"""Reconcile pre-extracted workflow capabilities into an unclassified primitive
pool. Return JSON {"operations": [...], "workflow_attribution": [...],
"candidate_attribution": [...]}.
Allowed operations are ADD, UPDATE, SKIP.

ADD and UPDATE must contain a complete `replacement`:
{"primitive_id":"<site>/<method>","method":"snake_case","capability":"...",
 "method_code":"<one or more Python method definitions, indented or unindented; the one public
 method definition must use the VALUE of the `method` field as its Python name (for example,
 if method is list_commits, write def list_commits(self, ...), NEVER def method(...)); private
 helper methods must start `_`>",
 "owns":[...],"does_not_own":[...],"input_contract":{...},"output_contract":{...},
 "requires":[...],"provides":[...],"supported_patterns":[...],
 "source_evidence":[{"workflow_id":"exact id","template_id":"exact id",
 "code_quote":"representative source excerpt or concise source description",
 "explanation":"what was generalized from the source"}]}.
UPDATE also has `target_id` and is valid only when capability identity and the core input/output
contract remain stable. It must return the entire replacement, never a patch. SKIP has `reason`.

Primitive boundary: own site selectors/endpoints/authentication/pagination and stable site-output
semantics; return typed objective facts. Do not return Locator, ElementHandle, raw DOM/HTML,
arbitrary page text, or untyped blobs. Workflows own requested filtering, subjective judgement,
aggregation, ranking/comparison, stopping specific to the question, and final formatting. No
generic regex/HTTP/browser setup primitives. Public primitives do not call other public
primitives; use requires/provides for environment-state preconditions.
Methods are generated for a feature component class whose __init__ stores `self.page`. Therefore
every generated method starts with `self`, uses `self.page` for browser access, and MUST NOT expose
a separate browser `page` parameter. The name `page` is reserved for that browser object: API/UI
pagination inputs must be named `page_number` (and represented that way in input_contract), never
`page`. Formatting seconds as an answer string is workflow logic; a site
primitive may instead parse a site's displayed duration into typed seconds.
Do not create `count_*` primitives that compute len/count over acquired records. Return typed
records and let the workflow aggregate them. A total explicitly supplied by the website may be
returned as an objective field alongside records.
Typed record schemas should be lossless with respect to stable objective fields demonstrated at
the acquisition boundary, not minimal projections tailored to the source task. Preserve distinct
identity fields, distinct site timestamps, stable hrefs/ids/state, and explicit pagination or
enumeration-completeness metadata when supported by evidence. Never claim a collection is complete
merely because the current source task stopped after one page.

Every workflow in the batch must occur exactly once in workflow_attribution:
{"workflow_id":"...","decision":"CONTRIBUTED","operation_indices":[0]} or
{"workflow_id":"...","decision":"SKIP","reason":"..."}.
Every supplied extracted candidate must occur exactly once in candidate_attribution:
{"candidate_id":"...","decision":"ADD|UPDATE","operation_index":0} or
{"candidate_id":"...","decision":"COVERED|REJECT","target_id":null|"existing id",
"reason":"specific reason"}. REJECT is allowed only for a boundary/evidence defect, not because
UI parsing is less attractive than an API. Every ADD/UPDATE operation must be linked from at least
one extracted candidate. Workflow attribution summarizes these candidate-level decisions.
Every ADD/UPDATE must cite supplied gold workflows and explain how concrete code was generalized.
Hard-coded project/product/date/branch values should become inputs when that preserves the site
operation. Source excerpts may be shortened or paraphrased; do not invent source workflows,
unsupported site behavior, or source answers.
The pool is candidate state; do not classify features and do not generate a package class yet."""

_CONSOLIDATE_SYS = r"""Consolidate and organize a complete candidate primitive pool for one
website. Return JSON {"operations":[...]}. Allowed operations: KEEP, MERGE, SPLIT.
Every input primitive must be consumed exactly once as a KEEP source, one MERGE source, or one
SPLIT source. Nothing may be silently deleted.

KEEP: {"op":"KEEP","source":"<id>","feature":"snake_case"}. It preserves code and contract.
MERGE: {"op":"MERGE","sources":["id1","id2",...],"feature":"snake_case",
 "replacement":<complete primitive object with id <site>/<feature>/<method>>,"reason":"..."}.
SPLIT: {"op":"SPLIT","source":"id","feature_assignments":[],
 "replacements":[<two or more complete primitive objects, each id <site>/<feature>/<method>>],
 "reason":"..."}. Each replacement carries complete generated method code, boundary contracts,
and source attribution with a concise explanation of any generalization.

Feature classes are composition components such as auth, reviews, commits, orders, or routes;
they are not inheritance subclasses. Choose cohesive site features. Preserve the primitive/workflow
boundary: site mechanics and typed parsing belong in primitives; task filtering, aggregation,
ranking, subjective decisions, and answer formatting remain in workflows. Do not alter KEEP code.
Do not emit package/class code; the deterministic Class Manager renders it."""

_QUALITY_SYS = r"""Act as an independent quality-and-coverage gate. Return JSON
{"verdicts":[{"operation_index":0,"verdict":"PASS|FAIL","reason":"..."}],
"rejection_verdicts":[{"candidate_id":"...","verdict":"PASS|FAIL","reason":"..."}]}.
Cover every ADD/UPDATE operation in verdicts and every candidate_attribution with decision REJECT
in rejection_verdicts exactly once. Do not repair code.

PASS requires: source evidence directly supports the site operation; output is typed; the method
owns site-specific acquisition/parsing but not task-specific filtering, aggregation, ranking,
subjective decisions, or answer formatting; owns and does_not_own are consistent; code and
contract agree. Parsing UI/DOM/page text internally into typed site records is valid and must not
be rejected merely because an API is unavailable. Parameterized site-native search/date/page
controls are valid; an arbitrary filter copied from the task question is not. FAIL unsupported,
invented, contradictory, overly task-specific, raw-output, or cosmetic abstractions.
Website-specific authentication mechanics are valid primitives when evidence demonstrates the
site's login URL/form selectors, submit behavior, and authenticated-state detection. Do not reject
such a candidate as generic browser setup merely because credentials are parameters.

FAIL a lossy task-tailored projection when the cited evidence demonstrates additional stable
objective record fields needed to interpret identity, time, state, links, or collection
completeness. FAIL an output that looks like a complete collection but neither traverses nor
reports pagination/completeness. Do not demand fields absent from the supplied evidence.

A REJECT passes only when removing task logic leaves no reusable website acquisition/parsing core.
If a count candidate demonstrates listing record IDs, it must be narrowed to a list-records
primitive, not rejected. If a candidate mixes authentication/report extraction/format shaping,
the demonstrated site report-row acquisition must be retained as a narrower primitive. A raw-text
output defect should be narrowed to typed facts when the evidence supports them. Mark such REJECT
decisions FAIL so the updater regenerates ADD/UPDATE instead."""


def _dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm(value: object) -> str:
    return " ".join(str(value or "").split())


def _template_escape_norm(value: object) -> str:
    """Normalize harmless template braces and model-added escaping before quote characters."""
    return (_norm(value).replace("{{", "{").replace("}}", "}")
            .replace('\\"', '"').replace("\\'", "'"))


def _hash(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def deduplicate_source_evidence(raw: dict) -> dict:
    """Remove repeated citations of one workflow without altering primitive semantics.

    Consolidation models sometimes copy multiple pre-merge evidence rows from the same workflow.
    The validator correctly requires one attribution row per workflow; retaining the first complete
    row is a mechanical normalization, not evidence invention or a quality repair.
    """
    for operation in raw.get("operations") or []:
        replacements = ([operation.get("replacement")] if operation.get("replacement")
                        else operation.get("replacements") or [])
        for replacement in replacements:
            if not isinstance(replacement, dict):
                continue
            evidence = replacement.get("source_evidence")
            if not isinstance(evidence, list):
                continue
            seen, unique = set(), []
            for row in evidence:
                workflow_id = str(row.get("workflow_id") or "") if isinstance(row, dict) else ""
                if workflow_id and workflow_id in seen:
                    continue
                if workflow_id:
                    seen.add(workflow_id)
                unique.append(row)
            replacement["source_evidence"] = unique
    return raw


def compose_candidate_indexes(
    *, site: str, indexes: list[dict], output: str | Path,
) -> dict:
    """Mechanically compose generated candidate indexes without rewriting primitive code."""
    by_id: dict[str, dict] = {}
    provenance = []
    for number, index in enumerate(indexes):
        if index.get("site") != site or index.get("status") != "candidate":
            raise ValueError(f"source index {number} is not a {site} candidate")
        provenance.append({"source": number, "primitive_ids": []})
        for primitive in index.get("primitives") or []:
            pid = primitive.get("primitive_id")
            if not pid:
                raise ValueError(f"source index {number} has primitive without id")
            provenance[-1]["primitive_ids"].append(pid)
            if pid in by_id and _hash(by_id[pid]) != _hash(primitive):
                raise ValueError(f"conflicting generated primitive: {pid}")
            by_id.setdefault(pid, deepcopy(primitive))
    primitives = sorted(by_id.values(), key=lambda item: item["primitive_id"])
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    index = {"site": site, "status": "candidate", "approved": False,
             "composition": provenance, "primitives": primitives}
    _dump(out / "index.json", index)
    (out / "package.py").write_text(render_site_package(site, primitives), encoding="utf-8")
    write_candidate_review(out, site=site, primitives=primitives)
    return index


def _op_kind(value: dict) -> str:
    """Canonicalize a harmless schema alias while retaining raw proposals on disk."""
    return str(value.get("op") or value.get("operation") or "").upper()


def partition_workflows(workflows: list[dict], *, batch_size: int, seed: int) -> list[list[dict]]:
    """Stable seeded partition, independent of manifest ordering."""
    ordered = sorted(workflows, key=lambda row: (str(row.get("template_id")), row.get("task_id", 0)))
    random.Random(seed).shuffle(ordered)
    return [ordered[i:i + batch_size] for i in range(0, len(ordered), batch_size)]


def validate_extraction(raw: dict, *, workflow: dict) -> list[str]:
    errors = []
    decision = str(raw.get("decision") or "").upper()
    candidates = raw.get("candidates") or []
    if decision == "SKIP":
        if candidates or raw.get("skip_category") not in {
            "BLOCKED", "NON_WEBSITE", "NO_REUSABLE_SITE_CAPABILITY"
        } or not str(raw.get("reason") or "").strip():
            errors.append("SKIP needs empty candidates, an allowed category, and a reason")
        return errors
    if decision != "CANDIDATES" or not candidates:
        return ["extraction must return non-empty CANDIDATES or a justified SKIP"]
    ids = []
    for i, candidate in enumerate(candidates):
        cid = candidate.get("candidate_id")
        method = candidate.get("proposed_method")
        ids.append(cid)
        if cid != f"{workflow['id']}::{method}" or not isinstance(method, str) or not _SAFE.fullmatch(method):
            errors.append(f"candidates[{i}] id/method invalid")
        for key in ("capability", "owns", "does_not_own", "input_contract", "output_contract",
                    "source_evidence"):
            if not candidate.get(key):
                errors.append(f"candidates[{i}].{key} must be non-empty")
        evidence = candidate.get("source_evidence") or {}
        if str(evidence.get("workflow_id")) != str(workflow["id"]):
            errors.append(f"candidates[{i}] evidence workflow mismatch")
        if str(evidence.get("template_id")) != str(workflow["template_id"]):
            errors.append(f"candidates[{i}] evidence template mismatch")
        quote = _norm(evidence.get("code_quote"))
        explanation = str(evidence.get("explanation") or "").strip()
        source = _norm(workflow.get("code"))
        if quote and quote in source:
            evidence["evidence_match_mode"] = "exact"
        elif quote and _template_escape_norm(quote) in _template_escape_norm(source):
            evidence["evidence_match_mode"] = "template_escape_equivalent"
        else:
            evidence["evidence_match_mode"] = "attributed_nonverbatim"
        if not quote or not explanation:
            errors.append(f"candidates[{i}] evidence needs a source reference and explanation")
    if len(ids) != len(set(ids)):
        errors.append("candidate ids must be unique")
    return errors


def _parse_methods(code: str, public_name: str) -> tuple[list[ast.stmt], list[str]]:
    wrapper = "class _Candidate:\n" + "\n".join(
        "    " + line if line.strip() else line for line in code.strip().splitlines()
    ) + "\n"
    try:
        tree = ast.parse(wrapper)
    except SyntaxError as exc:
        return [], [f"method_code does not parse: {exc}"]
    body = tree.body[0].body
    funcs = [x for x in body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]
    errors = []
    public = [x.name for x in funcs if not x.name.startswith("_")]
    if public != [public_name]:
        errors.append(f"method_code public methods must be exactly [{public_name!r}], got {public}")
    for fn in funcs:
        args = [arg.arg for arg in fn.args.args]
        if not args or args[0] != "self":
            errors.append(f"method {fn.name} must take self as its first argument")
        if fn.name == public_name and "page" in args[1:]:
            errors.append(
                f"public method {fn.name} must use self.page for the browser and may not expose "
                "an argument named page; rename a pagination input to page_number in both code "
                "and input_contract"
            )
    if len(funcs) != len(body):
        errors.append("method_code may contain only method definitions")
    return funcs, errors


def _schema_shape(value):
    """Remove prose descriptions before enforcing machine-readable output boundaries."""
    if isinstance(value, dict):
        return {key: _schema_shape(item) for key, item in value.items() if key != "description"}
    if isinstance(value, list):
        return [_schema_shape(item) for item in value]
    return value


def validate_primitive(value: dict, *, site: str, workflows: dict[str, dict], classified=False) -> list[str]:
    errors = []
    name = value.get("method")
    feature = value.get("feature") if classified else None
    expected_id = f"{site}/{feature}/{name}" if classified else f"{site}/{name}"
    if not isinstance(name, str) or not _SAFE.fullmatch(name):
        errors.append("method must be safe snake_case")
    if classified and (not isinstance(feature, str) or not _SAFE.fullmatch(feature)):
        errors.append("feature must be safe snake_case")
    if value.get("primitive_id") != expected_id:
        errors.append(f"primitive_id must be {expected_id!r}")
    for key in ("capability", "method_code", "owns", "does_not_own", "input_contract",
                "output_contract", "source_evidence"):
        if not value.get(key):
            errors.append(f"{key} must be non-empty")
    _, code_errors = _parse_methods(str(value.get("method_code") or ""), str(name or ""))
    errors.extend(code_errors)
    output = _norm(_schema_shape(value.get("output_contract"))).lower()
    if any(term in output for term in ("locator", "elementhandle", "raw dom", "raw_html",
                                       "raw html", "untyped text", "page text")):
        errors.append("output_contract exposes raw/untyped site output")
    boundary = _norm({"method": name, "capability": value.get("capability"),
                      "owns": value.get("owns")}).lower()
    if str(name or "").startswith("format_") or "final answer formatting" in boundary or (
        "format duration" in boundary and "parse" not in boundary
    ):
        errors.append("primitive owns workflow-level formatting rather than site-specific parsing")
    if str(name or "").startswith("count_") or "count unique" in boundary:
        errors.append("primitive computes workflow-level record aggregation; return typed records")
    evidence_rows = value.get("source_evidence") or []
    evidence_ids = [str(x.get("workflow_id")) for x in evidence_rows if isinstance(x, dict)]
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("source_evidence may cite each workflow at most once")
    for i, evidence in enumerate(evidence_rows):
        wid = str(evidence.get("workflow_id")) if isinstance(evidence, dict) else ""
        workflow = workflows.get(wid)
        if workflow is None:
            errors.append(f"evidence[{i}] cites unknown workflow")
            continue
        if str(evidence.get("template_id")) != str(workflow.get("template_id")):
            errors.append(f"evidence[{i}] template mismatch")
        quote = _norm(evidence.get("code_quote"))
        explanation = str(evidence.get("explanation") or "").strip()
        source = _norm(workflow.get("code"))
        if quote and quote in source:
            evidence["evidence_match_mode"] = "exact"
        elif quote and _template_escape_norm(quote) in _template_escape_norm(source):
            evidence["evidence_match_mode"] = "template_escape_equivalent"
        else:
            evidence["evidence_match_mode"] = "attributed_nonverbatim"
        if not quote or not explanation:
            errors.append(f"evidence[{i}] needs a source reference and explanation")
    return errors


def validate_quality_verdicts(
    raw: dict, operations: list[dict], candidate_attribution: list[dict] | None = None
) -> list[str]:
    expected = {
        i for i, operation in enumerate(operations) if _op_kind(operation) in {"ADD", "UPDATE"}
    }
    verdicts = raw.get("verdicts") or []
    seen = [x.get("operation_index") for x in verdicts if isinstance(x, dict)]
    errors = []
    if set(seen) != expected or len(seen) != len(set(seen)):
        errors.append("quality verdicts must cover every ADD/UPDATE operation exactly once")
        return errors
    for verdict in verdicts:
        if verdict.get("verdict") != "PASS":
            errors.append(
                f"quality gate rejected operation {verdict.get('operation_index')}: "
                + str(verdict.get("reason") or "no reason")
            )
    rejected = {
        str(x.get("candidate_id")) for x in (candidate_attribution or [])
        if str(x.get("decision") or "").upper() == "REJECT"
    }
    rejection_verdicts = raw.get("rejection_verdicts") or []
    rejection_ids = [str(x.get("candidate_id")) for x in rejection_verdicts if isinstance(x, dict)]
    if set(rejection_ids) != rejected or len(rejection_ids) != len(set(rejection_ids)):
        errors.append("rejection verdicts must cover every REJECT candidate exactly once")
    else:
        for verdict in rejection_verdicts:
            if verdict.get("verdict") != "PASS":
                errors.append(
                    f"coverage gate rejected dropping {verdict.get('candidate_id')}: "
                    + str(verdict.get("reason") or "no reason")
                )
    return errors


def validate_build_proposal(
    raw: dict, *, site: str, batch: list[dict], pool: dict[str, dict],
    all_workflows: dict[str, dict] | None = None, extractions: list[dict] | None = None,
):
    errors, accepted = [], []
    workflow_map = {str(x["id"]): x for x in batch}
    attrs = raw.get("workflow_attribution") or []
    attr_ids = [str(x.get("workflow_id")) for x in attrs if isinstance(x, dict)]
    if sorted(attr_ids) != sorted(workflow_map) or len(attr_ids) != len(set(attr_ids)):
        errors.append("workflow_attribution must cover every batch workflow exactly once")
    expected_candidates = {
        candidate["candidate_id"]
        for extraction in (extractions or [])
        for candidate in extraction.get("candidates") or []
    }
    candidate_attrs = raw.get("candidate_attribution") or []
    candidate_attr_ids = [str(x.get("candidate_id")) for x in candidate_attrs if isinstance(x, dict)]
    if extractions is not None and (
        sorted(candidate_attr_ids) != sorted(expected_candidates)
        or len(candidate_attr_ids) != len(set(candidate_attr_ids))
    ):
        errors.append("candidate_attribution must cover every extracted candidate exactly once")
    operations = raw.get("operations") or []
    for i, op in enumerate(operations):
        kind = _op_kind(op)
        if kind == "SKIP":
            accepted.append(op)
            continue
        if kind not in {"ADD", "UPDATE"}:
            errors.append(f"operations[{i}] unknown op {kind!r}")
            continue
        replacement = deepcopy(op.get("replacement") or {})
        item_errors = validate_primitive(
            replacement, site=site, workflows=all_workflows or workflow_map
        )
        target = op.get("target_id")
        if kind == "ADD" and replacement.get("primitive_id") in pool:
            item_errors.append("ADD target already exists")
        if kind == "UPDATE" and target not in pool:
            item_errors.append("UPDATE target does not exist")
        if kind == "UPDATE" and target in pool:
            old = pool[target]
            if replacement.get("primitive_id") != target:
                item_errors.append("UPDATE may not change primitive identity")
            if replacement.get("capability") != old.get("capability"):
                item_errors.append("UPDATE may not change capability identity")
            if replacement.get("input_contract") != old.get("input_contract") or replacement.get(
                "output_contract"
            ) != old.get("output_contract"):
                item_errors.append("UPDATE may not change the core input/output contract")
        if item_errors:
            errors.extend(f"operations[{i}]: {x}" for x in item_errors)
        else:
            canonical = deepcopy(op)
            canonical["op"] = kind
            canonical["replacement"] = replacement
            accepted.append(canonical)
    attributed_indices = set()
    for i, attr in enumerate(attrs):
        if not isinstance(attr, dict):
            continue
        wid = str(attr.get("workflow_id"))
        decision = attr.get("decision")
        indices = attr.get("operation_indices") or []
        if decision == "CONTRIBUTED":
            if not indices:
                errors.append(f"workflow_attribution[{i}] CONTRIBUTED needs operation_indices")
            for index in indices:
                if not isinstance(index, int) or index < 0 or index >= len(operations):
                    errors.append(f"workflow_attribution[{i}] has invalid operation index")
                    continue
                attributed_indices.add(index)
                evidence_ids = {
                    str(x.get("workflow_id"))
                    for x in (operations[index].get("replacement") or {}).get(
                        "source_evidence", []
                    ) if isinstance(x, dict)
                }
                if wid not in evidence_ids:
                    errors.append(
                        f"workflow_attribution[{i}] operation {index} lacks matching evidence"
                    )
        elif decision == "SKIP":
            if indices or not str(attr.get("reason") or "").strip():
                errors.append(f"workflow_attribution[{i}] invalid SKIP attribution")
        else:
            errors.append(f"workflow_attribution[{i}] unknown decision {decision!r}")
    semantic_indices = {
        i for i, op in enumerate(operations)
        if _op_kind(op) in {"ADD", "UPDATE"}
    }
    if attributed_indices != semantic_indices:
        errors.append("every ADD/UPDATE operation must be attributed to a batch workflow")
    candidate_operation_indices = set()
    for i, attr in enumerate(candidate_attrs):
        decision = str(attr.get("decision") or "").upper()
        if decision in {"ADD", "UPDATE"}:
            index = attr.get("operation_index")
            if not isinstance(index, int) or index not in semantic_indices:
                errors.append(f"candidate_attribution[{i}] has invalid operation_index")
            else:
                candidate_operation_indices.add(index)
        elif decision in {"COVERED", "REJECT"}:
            if not str(attr.get("reason") or "").strip():
                errors.append(f"candidate_attribution[{i}] {decision} needs a reason")
        else:
            errors.append(f"candidate_attribution[{i}] unknown decision {decision!r}")
    if extractions is not None and candidate_operation_indices != semantic_indices:
        errors.append("every ADD/UPDATE operation must be linked to an extracted candidate")
    return accepted, errors


def apply_build_operations(pool: dict[str, dict], operations: list[dict]) -> tuple[dict, list[dict]]:
    new = deepcopy(pool)
    diff = []
    for op in operations:
        kind = _op_kind(op)
        if kind not in {"ADD", "UPDATE"}:
            continue
        replacement = deepcopy(op["replacement"])
        pid = replacement["primitive_id"]
        before = new.get(pid)
        new[pid] = replacement
        diff.append({"op": kind, "primitive_id": pid, "before_hash": _hash(before) if before else None,
                     "after_hash": _hash(replacement)})
    return new, diff


def validate_consolidation(raw: dict, *, site: str, pool: dict[str, dict], workflows: dict[str, dict]):
    errors, consumed, final = [], [], []
    for i, op in enumerate(raw.get("operations") or []):
        kind = _op_kind(op)
        replacements = []
        if kind == "KEEP":
            source, feature = op.get("source"), op.get("feature")
            consumed.append(source)
            if source not in pool:
                errors.append(f"operations[{i}] KEEP source missing")
                continue
            replacement = deepcopy(pool[source])
            replacement["feature"] = feature
            replacement["primitive_id"] = f"{site}/{feature}/{replacement['method']}"
            replacements = [replacement]
        elif kind == "MERGE":
            sources = op.get("sources") or []
            consumed.extend(sources)
            if len(sources) < 2 or any(x not in pool for x in sources):
                errors.append(f"operations[{i}] MERGE sources invalid")
            replacement = deepcopy(op.get("replacement") or {})
            replacement.setdefault("feature", op.get("feature"))
            replacements = [replacement]
        elif kind == "SPLIT":
            source = op.get("source")
            consumed.append(source)
            if source not in pool or len(op.get("replacements") or []) < 2:
                errors.append(f"operations[{i}] SPLIT source/replacements invalid")
            replacements = deepcopy(op.get("replacements") or [])
        else:
            errors.append(f"operations[{i}] unknown op {kind!r}")
            continue
        for j, replacement in enumerate(replacements):
            item_errors = validate_primitive(
                replacement, site=site, workflows=workflows, classified=True
            )
            errors.extend(f"operations[{i}].replacements[{j}]: {x}" for x in item_errors)
            final.append(replacement)
    expected = sorted(pool)
    if sorted(consumed) != expected or len(consumed) != len(set(consumed)):
        errors.append(f"consolidation must consume every primitive exactly once; expected={expected}, got={consumed}")
    ids = [x.get("primitive_id") for x in final]
    if len(ids) != len(set(ids)):
        errors.append("final primitive ids must be unique")
    return final, errors, {"expected": expected, "consumed": consumed}


class _SelfHelperRewriter(ast.NodeTransformer):
    def __init__(self, renamed):
        self.renamed = renamed

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            node.attr = self.renamed.get(node.attr, node.attr)
        return node


def render_site_package(site: str, primitives: list[dict]) -> str:
    """Mechanically compose generated method ASTs into feature classes plus a root facade."""
    classes = []
    for feature in sorted({x["feature"] for x in primitives}):
        feature_items = [x for x in primitives if x["feature"] == feature]
        body = [ast.parse("def __init__(self, page):\n    self.page = page\n").body[0]]
        for primitive in sorted(feature_items, key=lambda x: x["method"]):
            funcs, errors = _parse_methods(primitive["method_code"], primitive["method"])
            if errors:
                raise ValueError("; ".join(errors))
            renamed = {x.name: f"_{primitive['method']}__{x.name.lstrip('_')}"
                       for x in funcs if x.name.startswith("_")}
            rewrite = _SelfHelperRewriter(renamed)
            for fn in funcs:
                fn.name = renamed.get(fn.name, fn.name)
                body.append(rewrite.visit(fn))
        prefix = "".join(part.capitalize() for part in site.split("_"))
        if site == "gitlab":
            prefix = "GitLab"
        classes.append(ast.ClassDef(name=prefix + "".join(x.capitalize() for x in feature.split("_")),
                                    bases=[], keywords=[], body=body, decorator_list=[]))
    root_body = [ast.parse("def __init__(self, page):\n    pass\n").body[0]]
    init = root_body[0]
    init.body = []
    for cls, feature in zip(classes, sorted({x["feature"] for x in primitives})):
        init.body.append(ast.parse(f"self.{feature} = {cls.name}(page)").body[0])
    if not init.body:
        init.body = [ast.Pass()]
    classes.append(ast.ClassDef(name=expected_class_name(site), bases=[], keywords=[],
                                body=root_body, decorator_list=[]))
    module = ast.Module(body=classes, type_ignores=[])
    ast.fix_missing_locations(module)
    code = '"""Generated candidate package; not promoted."""\n\n' + ast.unparse(module) + "\n"
    compile(code, f"{site}/package.py", "exec")
    return code


def write_candidate_review(path: str | Path, *, site: str, primitives: list[dict]) -> Path:
    path = Path(path)
    review = [f"# {site} candidate primitive package", "", "Status: candidate; not promoted.", "",
              "## Feature classes", ""]
    for feature in sorted({x["feature"] for x in primitives}):
        review.extend([f"### `{feature}`", ""])
        for primitive in sorted((x for x in primitives if x["feature"] == feature),
                                key=lambda x: x["primitive_id"]):
            review.extend([
                f"- `{primitive['primitive_id']}` — {primitive['capability']}",
                f"  - Owns: {', '.join(primitive.get('owns') or [])}",
                f"  - Does not own: {', '.join(primitive.get('does_not_own') or [])}",
                f"  - Evidence workflows: {', '.join(str(x.get('workflow_id')) for x in primitive.get('source_evidence') or [])}",
            ])
        review.append("")
    review.extend(["## Approval", "", "Review only. Editing generated package.py invalidates its hash.", ""])
    target = path / "review.md"
    target.write_text("\n".join(review), encoding="utf-8")
    return target


def retrieve_pool(batch: list[dict], pool: dict[str, dict], *, top_k: int = 12) -> list[dict]:
    """Cheap deterministic metadata retrieval; full code is exposed only for selected entries."""
    query = set(re.findall(r"[a-z0-9_]+", " ".join(str(x.get("intent", "")).lower()
                                                    for x in batch)))
    ranked = []
    for primitive in pool.values():
        text = " ".join([
            str(primitive.get("primitive_id", "")), str(primitive.get("capability", "")),
            " ".join(primitive.get("supported_patterns") or []),
        ]).lower()
        tokens = set(re.findall(r"[a-z0-9_]+", text))
        ranked.append((len(query & tokens), primitive["primitive_id"], primitive))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [deepcopy(row[2]) for row in ranked[:top_k]]


def build_audited_site_library(
    *, site: str, workflows: list[dict], output: str | Path, batch_size=8, seed=20260810,
    llm_fn: Callable[[str, str], dict], max_attempts: int = 3,
    resume_preconsolidation: bool = False,
) -> dict:
    """Run both phases and persist enough state to reproduce every transition."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    batches = partition_workflows(workflows, batch_size=batch_size, seed=seed)
    config = {"site": site, "batch_size": batch_size, "shuffle_seed": seed,
              "group_by": "site", "order_before_shuffle": ["template_id", "task_id"]}
    _dump(output / "config.json", config)
    _dump(output / "workflow_order.json", {
        "batches": [[{"id": x["id"], "task_id": x.get("task_id"),
                       "template_id": x.get("template_id")} for x in batch] for batch in batches]
    })
    pool, history = {}, []
    preconsolidation_path = output / "pre_consolidation" / "primitive_pool.json"
    if resume_preconsolidation and preconsolidation_path.is_file():
        previous = json.loads(preconsolidation_path.read_text(encoding="utf-8"))
        pool = {item["primitive_id"]: item for item in previous}
        history.append({"resume": "pre_consolidation", "primitive_count": len(pool)})
    all_workflows = {str(x["id"]): x for x in workflows}
    extractions_by_workflow = {}
    for workflow in workflows:
        directory = output / "extractions" / str(workflow["id"])
        existing_extraction = directory / "extraction.json"
        existing_validation = directory / "validation.json"
        if existing_extraction.exists() and existing_validation.exists():
            validation = json.loads(existing_validation.read_text(encoding="utf-8"))
            if validation.get("accepted") is True:
                extractions_by_workflow[str(workflow["id"])] = json.loads(
                    existing_extraction.read_text(encoding="utf-8")
                )
                continue
        inp = {"site": site, "workflow": workflow}
        _dump(directory / "input.json", inp)
        attempts, raw, errors = [], {}, []
        for attempt in range(1, max_attempts + 1):
            attempt_input = dict(inp)
            if errors:
                attempt_input.update({"previous_rejected_extraction": raw,
                                      "validation_feedback": errors,
                                      "retry_instruction": "Regenerate without losing demonstrated site capabilities."})
            raw = llm_fn(_EXTRACT_SYS, json.dumps(attempt_input, ensure_ascii=False)) or {}
            errors = validate_extraction(raw, workflow=workflow)
            attempts.append({"attempt": attempt, "proposal": raw, "errors": errors})
            if not errors:
                break
        _dump(directory / "attempts.json", attempts)
        _dump(directory / "extraction.json", raw)
        _dump(directory / "validation.json", {"accepted": not errors, "errors": errors})
        if errors:
            raise ValueError(f"{site} extraction {workflow['id']} rejected: {errors}")
        extractions_by_workflow[str(workflow["id"])] = raw
    pending_batches = [] if (resume_preconsolidation and pool) else batches
    for number, batch in enumerate(pending_batches):
        directory = output / "batches" / f"batch_{number:03d}"
        catalog_index = [{key: value.get(key) for key in (
            "primitive_id", "method", "capability", "input_contract", "output_contract",
            "supported_patterns")}
            for value in pool.values()]
        batch_extractions = [extractions_by_workflow[str(x["id"])] for x in batch]
        inp = {"site": site, "batch": batch, "extractions": batch_extractions,
               "catalog_index": catalog_index,
               "retrieved_primitives": retrieve_pool(batch, pool)}
        _dump(directory / "input.json", inp)
        attempts, raw, accepted, errors = [], {}, [], []
        for attempt in range(1, max_attempts + 1):
            attempt_input = dict(inp)
            if errors:
                attempt_input["previous_rejected_proposal"] = raw
                attempt_input["validation_feedback"] = errors
                attempt_input["retry_instruction"] = (
                    "Regenerate the complete proposal; correct every error without inventing "
                    "code or evidence."
                )
            raw = llm_fn(_BUILD_SYS, json.dumps(attempt_input, ensure_ascii=False)) or {}
            accepted, errors = validate_build_proposal(
                raw, site=site, batch=batch, pool=pool, all_workflows=all_workflows,
                extractions=batch_extractions,
            )
            quality = None
            if not errors:
                quality_input = {"review_kind": "primitive_boundary_quality", "site": site,
                                 "operations": raw.get("operations") or [],
                                 "candidate_attribution": raw.get("candidate_attribution") or [],
                                 "extractions": batch_extractions}
                quality = llm_fn(_QUALITY_SYS, json.dumps(quality_input, ensure_ascii=False)) or {}
                errors.extend(validate_quality_verdicts(
                    quality, raw.get("operations") or [], raw.get("candidate_attribution") or []
                ))
            attempts.append({"attempt": attempt, "proposal": raw,
                             "quality_verdicts": quality, "errors": errors})
            if not errors:
                break
        _dump(directory / "attempts.json", attempts)
        _dump(directory / "proposal.json", raw)
        _dump(directory / "validation.json", {"accepted": not errors, "errors": errors})
        _dump(directory / "workflow_attribution.json", raw.get("workflow_attribution") or [])
        if errors:
            raise ValueError(f"{site} batch {number} rejected: {errors}")
        pool, diff = apply_build_operations(pool, accepted)
        _dump(directory / "primitive_diff.json", diff)
        _dump(directory / "snapshot" / "primitive_pool.json", list(pool.values()))
        for primitive in pool.values():
            (directory / "snapshot" / "code").mkdir(parents=True, exist_ok=True)
            (directory / "snapshot" / "code" / f"{primitive['method']}.py").write_text(
                primitive["method_code"], encoding="utf-8"
            )
        history.append({"batch": number, "workflows": [x["id"] for x in batch], "diff": diff})
    _dump(output / "pre_consolidation" / "primitive_pool.json", list(pool.values()))
    consolidation_input = {"site": site, "primitive_pool": list(pool.values())}
    _dump(output / "consolidation" / "input.json", consolidation_input)
    attempts, raw, final, errors, coverage = [], {}, [], [], {}
    for attempt in range(1, max_attempts + 1):
        attempt_input = dict(consolidation_input)
        if errors:
            attempt_input["previous_rejected_proposal"] = raw
            attempt_input["validation_feedback"] = errors
            attempt_input["retry_instruction"] = (
                "Regenerate the complete consolidation. Correct coverage, boundary, code, and "
                "evidence errors without silently deleting a primitive."
            )
        raw = deduplicate_source_evidence(
            llm_fn(_CONSOLIDATE_SYS, json.dumps(attempt_input, ensure_ascii=False)) or {}
        )
        final, errors, coverage = validate_consolidation(
            raw, site=site, pool=pool, workflows=all_workflows
        )
        attempts.append({"attempt": attempt, "proposal": raw, "errors": errors})
        if not errors:
            break
    _dump(output / "consolidation" / "attempts.json", attempts)
    _dump(output / "consolidation" / "proposal.json", raw)
    _dump(output / "consolidation" / "validation.json", {"accepted": not errors, "errors": errors})
    _dump(output / "consolidation" / "coverage.json", coverage)
    if errors:
        raise ValueError(f"{site} consolidation rejected: {errors}")
    code = render_site_package(site, final)
    final_dir = output / "final_candidate"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "package.py").write_text(code, encoding="utf-8")
    index = {"schema_version": 1, "status": "candidate", "approved": False, "site": site,
             "root_class": expected_class_name(site), "primitives": final,
             "package_sha256": "sha256:" + hashlib.sha256(code.encode()).hexdigest()}
    _dump(final_dir / "index.json", index)
    _dump(final_dir / "primitive_pool.json", final)
    write_candidate_review(final_dir, site=site, primitives=final)
    audit = {"site": site, "status": "candidate", "history": history,
             "consolidation_operations": raw.get("operations") or [], "coverage": coverage}
    _dump(output / "audit.json", audit)
    return {"site": site, "status": "candidate", "batch_count": len(batches),
            "pre_consolidation_count": len(pool), "final_count": len(final),
            "package": str(final_dir / "package.py")}
