"""Audited two-phase builder for website primitive packages.

Phase 1 extracts workflows and proposes independent primitive candidates in parallel. Phase 2
performs one KEEP/MERGE/SPLIT pass over their union and assigns feature classes. All LLM output is retained;
the deterministic manager validates and renders candidates but never invents primitive code.
"""
from __future__ import annotations

import ast
import hashlib
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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
 "guarantees":{"collection_scope":"single|page|query|scope|not_applicable",
 "completeness":"complete|partial|conditional|not_applicable",
 "supports_absence_proof":true|false,
 "configuration":{"kind":"none|internal|semantic_enum","supported_values":[],
 "coupled_site_parameters_hidden":true}},"acceptance_checks":["runtime postcondition",...],
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

Candidate-set acquisition mechanics are also website operations when the workflow demonstrates
them and they can be parameterized without embedding the task's category decision. Examples are
issuing several caller-supplied queries, combining bounded and unbounded site searches, deduplicating
site records by stable identity, and preserving objective coordinates returned by the site. Extract
that reusable acquisition core separately from the workflow's choice of query terms, category
filter, nearest/all decision, ranking, and answer formatting. A single query-scoped search must not
claim that it exhaustively discovers the candidates required by a nearest/all/vicinity task.
Client-side haversine/distance computation is generic workflow comparison, not a site primitive,
unless the website itself returns that distance as part of the acquired record.
Coverage requirement: when source code issues two or more place/list searches in a loop and merges
or deduplicates their records before applying task-specific filters, emit a separate candidate for
that multi-search acquisition pattern. Do not reduce it to only the one-query endpoint candidate,
and do not push the demonstrated request-loop/dedup mechanics back into `does_not_own`.

Do not overfit a typed record to only the fields consumed by the current task. At the same
demonstrated acquisition boundary, preserve stable objective identity, temporal, state, value,
link, and pagination/completeness fields that the evidence actually exposes. This is not license
to invent undocumented fields. In particular, do not collapse contributor identity to display
name, issue records to title/href, commit timestamps to one ambiguous date field, or paginated
search results to an apparently complete list when richer facts/completeness are demonstrated.
Reserve the input name `page` for the component's browser object (`self.page`). Describe numeric
pagination inputs as `page_number` in candidate input contracts.
Do not expose a serialized geographic viewbox string. Represent bounds as a typed object with
minlon, minlat, maxlon, and maxlat numeric fields; validate minlon < maxlon and minlat < maxlat,
then serialize in the site-required order inside the primitive. This ordering is site request
construction, not workflow logic.

A website package owns mechanisms of that website deployment. When the source tries both the
site-local endpoint/UI and unrelated public fallback providers, extract the site-local mechanism;
do not turn public Photon, public Nominatim, maps.co, or another third-party workaround into a
provider switch in this site's primitive. Preserve the failed/fallback attempt as provenance, not
as a supported site capability. If several source paths hit the same site acquisition and differ
only in requested fields, pagination, or projection, expose the richest evidence-supported typed
site-local boundary rather than separate lossy variants.

Guarantees describe only what the demonstrated acquisition can establish. Ranked or page-scoped
collections do not support absence proof. If site deployment parameters are coupled (for example
transport mode to endpoint/port/profile), expose one semantic enum and resolve the coupling inside
the primitive; never expose independently combinable low-level controls. Acceptance checks state
observable postconditions that distinguish valid empty output from acquisition failure.
Hard invariant: `supports_absence_proof` may be true only when `completeness` is exactly
`complete`. For page-, query-, bounded-, partial-, or conditional acquisition it must be false,
even when the source workflow happened to find no matching record. Absence in one acquired slice
is not proof of site-wide absence.

Do not compare against a library, merge candidates, generate code, or discard a real capability
merely because an API/embedded JSON source would be more stable. Source evidence is attribution,
not a demand to copy code verbatim: explicitly describe parameterization of hard-coded instance
values and removal of task-specific logic."""

_BUILD_SYS = r"""Reconcile pre-extracted workflow capabilities into an unclassified primitive
pool. Return JSON {"operations": [...], "workflow_attribution": [...],
"candidate_attribution": [...]}.
Allowed operations are ADD, UPDATE, SKIP.
Hard schema invariant: every object in top-level `operations` has `op` equal to exactly ADD,
UPDATE, or SKIP. `COVERED` and `REJECT` are candidate-attribution decisions only and must never
appear as an operation or in an operation's `op` field. A covered candidate emits no operation;
record it only in `candidate_attribution` with its existing `target_id`.

ADD and UPDATE must contain a complete `replacement`:
{"primitive_id":"<site>/<method>","method":"snake_case","capability":"...",
 "method_code":"<one or more Python method definitions, indented or unindented; the one public
 method definition must use the VALUE of the `method` field as its Python name (for example,
 if method is list_commits, write def list_commits(self, ...), NEVER def method(...)); private
 helper methods must start `_`>",
 "owns":[...],"does_not_own":[...],"input_contract":{...},"output_contract":{...},
 "requires":[...],"provides":[...],"supported_patterns":[...],
 "guarantees":{"collection_scope":"single|page|query|scope|not_applicable",
 "completeness":"complete|partial|conditional|not_applicable",
 "supports_absence_proof":true|false,
 "configuration":{"kind":"none|internal|semantic_enum","supported_values":[],
 "coupled_site_parameters_hidden":true}},"acceptance_checks":["runtime postcondition",...],
 "source_evidence":[{"workflow_id":"exact id","template_id":"exact id",
 "code_quote":"representative source excerpt or concise source description",
 "explanation":"what was generalized from the source"}]}.
UPDATE also has `target_id` and is valid only when capability identity and the core input/output
contract remain stable. It must return the entire replacement, never a patch. SKIP has `reason`.
UPDATE is additive: preserve every existing required input name and shape and every existing output
field. If generalization would replace origin/destination with waypoints, rename inputs, narrow an
enum, or otherwise make old calls invalid, emit a separate ADD (or keep the narrower target) rather
than a breaking UPDATE.
For every UPDATE, copy the target primitive's existing `capability` text verbatim at the beginning
of `replacement.capability`; append any newly supported behavior only after that exact prefix. Never
paraphrase, reorder, shorten, or replace the existing capability sentence. This is a mechanical
backward-compatibility requirement, not a request to choose a better description.
When the input has `build_mode: parallel_initial`, every batch sees the same frozen empty catalog:
emit only ADD or SKIP operations. Do not assume another batch's candidates exist and do not use
arrival order to choose granularity. Independently preserve every reusable capability evidenced in
this batch; the later global consolidation resolves duplicate, overlapping, or differently-grained
candidates across batches.

Primitive boundary: own site selectors/endpoints/authentication/pagination and stable site-output
semantics; return typed objective facts. Do not return Locator, ElementHandle, raw DOM/HTML,
arbitrary page text, or untyped blobs. Workflows own requested filtering, subjective judgement,
aggregation, ranking/comparison, stopping specific to the question, and final formatting. No
generic regex/HTTP/browser setup primitives. Public primitives do not call other public
primitives; use requires/provides for environment-state preconditions.
Authentication implementation artifacts such as raw CSRF/form keys, session cookies, and bearer
tokens are private mechanics, not stable public outputs. A primitive may return typed facts such
as `is_authenticated`, the post-login URL, or whether a required token was observed, but it must
not expose the token value. When an extracted candidate exposes such a value while an existing
primitive already covers the safe authentication operation, treat that internal field as a
boundary defect rather than widening the public contract merely to preserve it.
Parameterized candidate-set acquisition may own repeated site requests, bounded/unbounded search,
and stable-ID deduplication when source workflows demonstrate those mechanics. It must leave
query/category terms, client-computed distance, semantic inclusion, ranking, and final selection
to the workflow. Keep this distinct from a one-query primitive: the latter is query-scoped and
cannot promise candidate-set completeness for open-ended nearest/all/vicinity requests.
Do not REJECT such an extracted candidate merely because its one source workflow used concrete
task terms (for example USPS) or because only one workflow demonstrates it. When those terms have
been lifted into caller inputs and task filtering/selection remains outside, preserve the evidenced
acquisition mechanism as ADD or a genuinely backward-compatible UPDATE.
Methods are generated for a feature component class whose __init__ stores `self.page`. Therefore
every generated method starts with `self`, uses `self.page` for browser access, and MUST NOT expose
a separate browser `page` parameter. The name `page` is reserved for that browser object: API/UI
pagination inputs must be named `page_number` (and represented that way in input_contract), never
`page`. Formatting seconds as an answer string is workflow logic; a site
primitive may instead parse a site's displayed duration into typed seconds.
Geographic bounds/viewbox inputs must be typed objects with numeric minlon, minlat, maxlon, and
maxlat fields. The method validates increasing longitude/latitude bounds and serializes the opaque
site parameter internally; never expose the raw comma-separated viewbox string as a public input.
Do not create `count_*` primitives that compute len/count over acquired records. Return typed
records and let the workflow aggregate them. A total explicitly supplied by the website may be
returned as an objective field alongside records.
Typed record schemas should be lossless with respect to stable objective fields demonstrated at
the acquisition boundary, not minimal projections tailored to the source task. Preserve distinct
identity fields, distinct site timestamps, stable hrefs/ids/state, and explicit pagination or
enumeration-completeness metadata when supported by evidence. Never claim a collection is complete
merely because the current source task stopped after one page.
Hard invariant: set `supports_absence_proof` to true only when `completeness` is exactly
`complete`; otherwise set it to false. A valid empty page, query, bounded scan, or conditional
collection is not an absence proof outside that explicitly complete acquisition scope.
Every replacement must state machine-readable guarantees and observable acceptance checks. A
configuration contract may be `semantic_enum` only when code accepts the semantic parameter,
internally maps every supported value to coupled deployment controls, and checks the response.
Never expose coupled endpoint/port/profile controls as independently combinable public inputs.
Do not infer a configuration contradiction merely because a low-level path/profile label remains
constant while another coupled deployment control (such as endpoint or port) changes. When
successful source workflows demonstrate the semantic modes, hide the complete evidenced mapping
behind one semantic enum rather than exposing or interpreting its low-level pieces independently.
Do not expose unrelated public fallback services as a semantic provider enum for a site package.
Prefer the evidenced site-local endpoint or UI. A declared output field is valid only when the
generated request and parser actually acquire it: for example, a geocoder cannot promise postcode
or structured address fields unless it requests address details and parses the returned address.

Every workflow in the batch must occur exactly once in workflow_attribution:
{"workflow_id":"...","decision":"CONTRIBUTED","operation_indices":[0]} or
{"workflow_id":"...","decision":"SKIP","reason":"..."}.
Every supplied extracted candidate must occur exactly once in candidate_attribution:
{"candidate_id":"...","decision":"ADD|UPDATE","operation_index":0} or
{"candidate_id":"...","decision":"COVERED|REJECT","target_id":null|"existing id",
"reason":"specific reason"}. REJECT is allowed only for a boundary/evidence defect, not because
UI parsing is less attractive than an API. COVERED is valid only when the target primitive
subsumes the candidate's demonstrated acquisition and typed output. If new evidence adds objective
output fields or supported configurations, use a backward-compatible UPDATE rather than COVERED.
Before returning, mechanically compare the IDs in the input with the two attribution arrays:
copy every input batch `workflow_id` exactly once into `workflow_attribution`, and copy every input
extracted `candidate_id` exactly once into `candidate_attribution`. Do not omit an ID because it is
covered, rejected, or contributes no operation; represent that outcome with the appropriate
attribution decision. Do not invent, normalize, rename, or duplicate either kind of ID.
Raw `row_text`, page text, or a generic snippet does not subsume separately extracted typed fields.
For example, a target returning only `row_text` and `product_name` does not cover a candidate that
also exposes `nickname` and `summary`: widen the generated target's typed schema and parser, or
generate a separate ADD. Never keep returning COVERED after validation reports dropped fields.
Every ADD/UPDATE operation must be linked from at least one extracted candidate. Workflow
attribution summarizes these candidate-level decisions.
Within one batch, do not emit two primitives when one is a lossy subset of the other site
operation. Emit the richer evidence-supported primitive once and point every subsumed candidate
to that operation (ADD/UPDATE) or mark it COVERED by that generated target. In particular, if two
candidates read the same detail page, preserve the union of demonstrated stable objective fields.
`supports_absence_proof` must remain false unless the code explicitly distinguishes a valid
not-found response from navigation, authentication, acquisition, and parser failures.
Every ADD/UPDATE must cite supplied gold workflows and explain how concrete code was generalized.
Hard-coded project/product/date/branch values should become inputs when that preserves the site
operation. Source excerpts may be shortened or paraphrased; do not invent source workflows,
unsupported site behavior, or source answers.
The pool is candidate state; do not classify features and do not generate a package class yet."""

_CONSOLIDATE_SYS = r"""Consolidate and organize a complete candidate primitive pool for one
website. Return JSON {"operations":[...]}. Allowed operations: KEEP, MERGE, SPLIT.
Every input primitive must be consumed exactly once as a KEEP source, one MERGE source, or one
SPLIT source. Nothing may be silently deleted.

Each input row has a manager-assigned `candidate_key`. Use that exact key in KEEP `source`, MERGE
`sources`, and SPLIT `source`; `primitive_id` is capability identity and may be duplicated across
independently generated batches. Resolve those duplicates here rather than silently overwriting.

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
MERGE/SPLIT replacements preserve or strengthen explicit guarantees and acceptance checks. Do not
turn conflicting configuration evidence into freely combinable public parameters; use a semantic
enum with an internal mapping, or keep the capability narrower.
MERGE overlapping acquisition primitives that address the same site resource even when their
input names, provider wrappers, or output projections differ. The replacement should keep one
site-local mechanism and the lossless union of evidence-supported objective fields. Do not KEEP
multiple geocoders/searchers merely because one is a lossy projection or exposes an external
fallback provider. A site package must not depend on unrelated public services when an evidenced
site-local mechanism exists. Verify that every promised output field is enabled by the request
and populated by the parser; otherwise repair it in the MERGE replacement or omit the unsupported
field.
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
PASS a source-evidenced candidate-acquisition primitive that accepts caller-supplied query terms,
performs repeated/bounded site searches, deduplicates stable records, and returns site facts;
those are acquisition mechanics, not task filtering. FAIL it if it hard-codes the source task's
category, adds generic client-side distance/ranking logic, or claims exhaustive nearest/all coverage
without an evidenced completeness mechanism.
FAIL a primitive that exposes a geographic viewbox/bounds as an opaque serialized string or does
not validate coordinate ordering before constructing the site request.
Website-specific authentication mechanics are valid primitives when evidence demonstrates the
site's login URL/form selectors, submit behavior, and authenticated-state detection. Do not reject
such a candidate as generic browser setup merely because credentials are parameters.

FAIL a lossy task-tailored projection when the cited evidence demonstrates additional stable
objective record fields needed to interpret identity, time, state, links, or collection
completeness. FAIL an output that looks like a complete collection but neither traverses nor
reports pagination/completeness. Do not demand fields absent from the supplied evidence.
FAIL missing, unsupported, or internally inconsistent guarantees/acceptance checks. FAIL when
coupled site configuration is exposed as independent public controls, when `semantic_enum` lacks
an internal mapping for every supported value, or when valid empty output cannot be distinguished
from acquisition/filter/parser failure.
Do not reject an evidenced semantic configuration solely because one low-level path/profile label
looks inconsistent with that semantic name; inspect the whole coupled mapping demonstrated by the
successful source workflow.
FAIL a site primitive that exposes unrelated public fallback providers when an evidenced
site-local endpoint or UI implements the capability. FAIL a declared typed output whose source
data is not requested or parsed by the method code. When several operations in the same batch are
lossy/overlapping views of one site acquisition, FAIL the lossy duplication so the updater emits
one richer operation; global duplicates from independent parallel batches are resolved by the
serial consolidation stage.

A REJECT passes only when removing task logic leaves no reusable website acquisition/parsing core.
If a count candidate demonstrates listing record IDs, it must be narrowed to a list-records
primitive, not rejected. If a candidate mixes authentication/report extraction/format shaping,
the demonstrated site report-row acquisition must be retained as a narrower primitive. A raw-text
output defect should be narrowed to typed facts when the evidence supports them. Mark such REJECT
decisions FAIL so the updater regenerates ADD/UPDATE instead."""


def _dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_consolidation_response(raw: object) -> dict:
    """Accept harmless wrapper variation while leaving semantic validation untouched."""
    if isinstance(raw, list):
        return {"operations": raw}
    if not isinstance(raw, dict):
        return {"operations": []}
    if isinstance(raw.get("operations"), list):
        return raw
    if raw.get("op") in {"KEEP", "MERGE", "SPLIT"}:
        return {"operations": [raw]}
    return raw


def _norm(value: object) -> str:
    return " ".join(str(value or "").split())


def _template_escape_norm(value: object) -> str:
    """Normalize harmless template braces and model-added escaping before quote characters."""
    return (_norm(value).replace("{{", "{").replace("}}", "}")
            .replace('\\"', '"').replace("\\'", "'"))


def _hash(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


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


def _normalize_operation_envelopes(value: dict) -> dict:
    """Canonicalize {"ADD": {...}} without modifying generated primitive contents."""
    if not isinstance(value, dict) or not isinstance(value.get("operations"), list):
        return value
    result = deepcopy(value)
    original = deepcopy(result["operations"])
    changed = False
    normalized = []
    for operation in result["operations"]:
        if isinstance(operation, dict) and not _op_kind(operation):
            keys = [key for key in ("ADD", "UPDATE", "SKIP") if key in operation]
            if len(keys) == 1 and isinstance(operation[keys[0]], dict):
                operation = {"op": keys[0], **deepcopy(operation[keys[0]])}
                changed = True
        normalized.append(operation)
    if changed:
        result["model_operations"] = original
        result["operations"] = normalized
    return result


def _normalize_extraction(value: dict) -> dict:
    """Repair the common harmless omission of the CANDIDATES envelope."""
    if (
        isinstance(value, dict)
        and not value.get("decision")
        and not value.get("candidates")
        and value.get("candidate_id")
        and value.get("proposed_method")
    ):
        return {"decision": "CANDIDATES", "candidates": [value]}
    return value


def _reconcile_workflow_attribution(value: dict, batch: list[dict]) -> dict:
    """Derive workflow attribution from replacement evidence, the provenance source of truth."""
    if not isinstance(value, dict) or not isinstance(value.get("operations"), list):
        return value
    result = deepcopy(value)
    original = result.get("workflow_attribution") or []
    original_by_id = {
        str(row.get("workflow_id")): row for row in original if isinstance(row, dict)
    }
    evidence_by_operation = []
    for operation in result["operations"]:
        evidence_by_operation.append({
            str(row.get("workflow_id"))
            for row in (operation.get("replacement") or {}).get("source_evidence", [])
            if isinstance(row, dict)
        })
    reconciled = []
    for workflow in batch:
        workflow_id = str(workflow["id"])
        indices = [
            index for index, evidence_ids in enumerate(evidence_by_operation)
            if workflow_id in evidence_ids
        ]
        if indices:
            reconciled.append({"workflow_id": workflow_id, "decision": "CONTRIBUTED",
                               "operation_indices": indices})
        else:
            prior = original_by_id.get(workflow_id) or {}
            reason = str(prior.get("reason") or "").strip() or (
                "No generated ADD/UPDATE replacement cites this workflow as source evidence."
            )
            reconciled.append({"workflow_id": workflow_id, "decision": "SKIP",
                               "reason": reason})
    if original != reconciled:
        result["model_workflow_attribution"] = original
        result["workflow_attribution"] = reconciled
    return result


def _drop_unlinked_semantic_operations(value: dict) -> dict:
    """Drop model operations that no extracted candidate claims.

    Candidate attribution is the auditable boundary of the batch builder.  An
    operation backed only by a workflow citation, but by no extracted
    candidate, is a newly invented capability rather than a reconciliation of
    extraction output.  Removing it is a schema normalization; primitive code
    and contracts that remain are still entirely model generated.
    """
    if not isinstance(value, dict) or not isinstance(value.get("operations"), list):
        return value
    result = deepcopy(value)
    operations = result["operations"]
    candidate_attrs = result.get("candidate_attribution") or []
    linked = {
        row.get("operation_index")
        for row in candidate_attrs
        if isinstance(row, dict)
        and str(row.get("decision") or "").upper() in {"ADD", "UPDATE"}
        and isinstance(row.get("operation_index"), int)
    }
    keep_indices = [
        index for index, operation in enumerate(operations)
        if _op_kind(operation) not in {"ADD", "UPDATE"} or index in linked
    ]
    if len(keep_indices) == len(operations):
        return result
    remap = {old: new for new, old in enumerate(keep_indices)}
    dropped = [
        {"operation_index": index,
         "primitive_id": (operation.get("replacement") or {}).get("primitive_id"),
         "reason": "no extracted candidate attribution links this operation"}
        for index, operation in enumerate(operations) if index not in remap
    ]
    result["model_operations_before_candidate_link_filter"] = deepcopy(operations)
    result["operations"] = [operations[index] for index in keep_indices]
    for row in result.get("candidate_attribution") or []:
        index = row.get("operation_index")
        if isinstance(index, int) and index in remap:
            row["operation_index"] = remap[index]
    for row in result.get("workflow_attribution") or []:
        indices = row.get("operation_indices")
        if isinstance(indices, list):
            row["operation_indices"] = [remap[index] for index in indices if index in remap]
    result.setdefault("manager_normalizations", []).append({
        "kind": "drop_unlinked_semantic_operations", "dropped": dropped,
    })
    return result


def _normalize_safe_guarantee_weakening(value: dict) -> dict:
    """Mechanically remove an impossible absence claim without inventing behavior or code."""
    if not isinstance(value, dict) or not isinstance(value.get("operations"), list):
        return value
    result = deepcopy(value)
    normalizations = list(result.get("manager_normalizations") or [])
    for index, operation in enumerate(result["operations"]):
        replacement = operation.get("replacement") or {}
        guarantees = replacement.get("guarantees") or {}
        if (guarantees.get("supports_absence_proof") is True
                and guarantees.get("completeness") != "complete"):
            guarantees["supports_absence_proof"] = False
            normalizations.append({
                "operation_index": index,
                "field": "guarantees.supports_absence_proof",
                "from": True,
                "to": False,
                "reason": "absence proof is impossible without complete acquisition",
            })
    if normalizations:
        result["manager_normalizations"] = normalizations
    return result


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
                    "guarantees", "acceptance_checks", "source_evidence"):
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


def _contract_is_backward_compatible(old: dict, new: dict, *, input_contract: bool) -> bool:
    """Allow additive contract widening while rejecting changes that break existing consumers."""
    old_shape, new_shape = _schema_shape(old), _schema_shape(new)

    def compatible(old_value, new_value):
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            old_properties = old_value.get("properties")
            new_properties = new_value.get("properties")
            if isinstance(old_properties, dict):
                if not isinstance(new_properties, dict) or not set(old_properties).issubset(
                    new_properties
                ):
                    return False
                if any(not compatible(old_properties[name], new_properties[name])
                       for name in old_properties):
                    return False
                old_required = set(old_value.get("required") or [])
                new_required = set(new_value.get("required") or [])
                if input_contract and not new_required.issubset(old_required):
                    return False
                if not input_contract and not old_required.issubset(new_required):
                    return False
            for key, old_child in old_value.items():
                if key in {"properties", "required"}:
                    continue
                if key not in new_value or not compatible(old_child, new_value[key]):
                    return False
            return True
        if isinstance(old_value, list) and isinstance(new_value, list):
            return old_value == new_value
        return old_value == new_value

    return compatible(old_shape, new_shape)


def _semantic_output_fields(value) -> set[str]:
    """Collect normalized objective field names from JSON-schema and compact field schemas."""
    aliases = {
        "places": "results", "candidates": "results", "products": "results",
        "lat": "latitude", "lon": "longitude",
        "type": "place_type", "class": "category",
        "issue_url": "web_url",
        "detail_url": "order_detail_url",
        "display_date": "order_date", "order_date_text": "order_date",
        "display_order_date": "order_date", "order_date_display": "order_date",
        "display_order_total": "order_total", "order_total_display": "order_total",
        "total_text": "order_total",
        "status_text": "status", "status_display": "status", "display_status": "status",
        "grand_total_text": "grand_total", "grand_total_display": "grand_total",
        "review_title": "title", "review_content": "description",
        "summary": "title", "review_text": "detail",
        "review_id": "id",
        "product_name": "product", "product_url": "url",
        # Magento GraphQL exposes this as
        # price_range.minimum_price.final_price.value.  Some extractors flatten the path.
        "minimum_final_price_value": "value",
        "authenticated": "is_authenticated",
        "dashboard_url": "final_url",
        "session_authenticated": "is_authenticated",
        "landing_url": "final_url", "post_login_url": "final_url",
        "account_home_url": "final_url",
        "records": "results", "orders": "results",
    }
    # These are private authentication mechanics, not reusable semantic outputs.  They may be
    # acquired and consumed inside a primitive, but must not force a public contract to expose
    # credentials/tokens merely because a source workflow kept them in a local variable.
    internal_auth_fields = {
        "form_key", "csrf_token", "csrfmiddlewaretoken", "xsrf_token",
        "session_cookie", "session_cookies", "access_token", "bearer_token",
    }
    ignored = {"type", "items", "properties", "fields", "required", "description", "enum",
               "default", "anyOf", "oneOf", "allOf", "format"}
    fields = set()
    if isinstance(value, dict):
        for container in ("properties", "fields"):
            children = value.get(container)
            if isinstance(children, dict):
                for name, child in children.items():
                    if name.lower() in internal_auth_fields:
                        continue
                    # Object/array wrapper names are shape, not objective output facts. Compare
                    # their typed leaves so `{review:{...}}` can cover the equivalent flat schema.
                    structured = isinstance(child, (dict, list)) and (
                        isinstance(child, list)
                        or any(key in child for key in ("properties", "fields", "items"))
                    )
                    if not structured:
                        fields.add(aliases.get(name, name))
                    fields.update(_semantic_output_fields(child))
        for name, child in value.items():
            if name not in ignored and name not in {"properties", "fields"}:
                if name.lower() in internal_auth_fields:
                    continue
                structured = isinstance(child, (dict, list)) and (
                    isinstance(child, list)
                    or any(key in child for key in ("properties", "fields", "items"))
                )
                if not structured:
                    fields.add(aliases.get(name, name))
                fields.update(_semantic_output_fields(child))
            elif name in {"items", "anyOf", "oneOf", "allOf"}:
                fields.update(_semantic_output_fields(child))
    elif isinstance(value, list):
        for child in value:
            fields.update(_semantic_output_fields(child))
    ignored_fields = {
        "profile", "origin_latitude", "origin_longitude", "destination_latitude",
        "destination_longitude", "nullable", "page_text_excerpt", "page_title",
        "detected_markers",
    }
    return {
        name for name in fields
        if name not in ignored_fields and not name.startswith("raw_") and not name.endswith("_path")
    }


def _validate_guarantees(value: dict) -> list[str]:
    errors = []
    guarantees = value.get("guarantees")
    if not isinstance(guarantees, dict):
        return ["guarantees must be an object"]
    required = {"collection_scope", "completeness", "supports_absence_proof", "configuration"}
    if set(guarantees) != required:
        errors.append(f"guarantees keys must be exactly {sorted(required)}")
    if guarantees.get("collection_scope") not in {
        "single", "page", "query", "scope", "not_applicable"
    }:
        errors.append("guarantees.collection_scope is invalid")
    completeness = guarantees.get("completeness")
    if completeness not in {"complete", "partial", "conditional", "not_applicable"}:
        errors.append("guarantees.completeness is invalid")
    absence = guarantees.get("supports_absence_proof")
    if not isinstance(absence, bool):
        errors.append("guarantees.supports_absence_proof must be boolean")
    elif absence and completeness != "complete":
        errors.append("absence proof requires complete acquisition")
    configuration = guarantees.get("configuration")
    if not isinstance(configuration, dict):
        errors.append("guarantees.configuration must be an object")
    else:
        config_required = {"kind", "supported_values", "coupled_site_parameters_hidden"}
        if set(configuration) != config_required:
            errors.append(f"guarantees.configuration keys must be exactly {sorted(config_required)}")
        kind = configuration.get("kind")
        values = configuration.get("supported_values")
        if kind not in {"none", "internal", "semantic_enum"}:
            errors.append("guarantees.configuration.kind is invalid")
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            errors.append("guarantees.configuration.supported_values must be strings")
        elif kind == "semantic_enum" and not values:
            errors.append("semantic_enum configuration requires supported_values")
        if configuration.get("coupled_site_parameters_hidden") is not True:
            errors.append("coupled site parameters must be hidden")
        properties = (value.get("input_contract") or {}).get("properties") or {}
        config_names = {"provider", "backend", "profile", "transport_mode", "mode", "engine",
                        "service"}
        config_values = {
            str(item)
            for name, spec in properties.items()
            if name in config_names and isinstance(spec, dict)
            for item in (spec.get("enum") or [])
        }
        if config_values and kind != "semantic_enum":
            errors.append("public configuration enum requires semantic_enum guarantees")
        if config_values and set(values or []) != config_values:
            errors.append("guarantees supported_values must match public configuration enum")
    checks = value.get("acceptance_checks")
    if not isinstance(checks, list) or not checks or any(
        not isinstance(item, str) or not item.strip() for item in checks
    ):
        errors.append("acceptance_checks must be non-empty strings")
    return errors


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
                "output_contract", "guarantees", "acceptance_checks", "source_evidence"):
        if not value.get(key):
            errors.append(f"{key} must be non-empty")
    errors.extend(_validate_guarantees(value))

    def viewbox_specs(schema):
        if not isinstance(schema, dict):
            return
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for field_name, field_schema in properties.items():
                if field_name == "viewbox":
                    yield field_schema
                yield from viewbox_specs(field_schema)
        yield from viewbox_specs(schema.get("items"))

    for spec in viewbox_specs(value.get("input_contract")):
        required_bounds = {"minlon", "minlat", "maxlon", "maxlat"}
        if not isinstance(spec, dict) or spec.get("type") != "object":
            errors.append("viewbox input must be a typed bounds object, not a serialized string")
            continue
        properties = spec.get("properties") or {}
        if not required_bounds.issubset(properties) or not required_bounds.issubset(
            set(spec.get("required") or [])
        ):
            errors.append("viewbox object must require minlon, minlat, maxlon, and maxlat")
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
    method_code = str(value.get("method_code") or "")
    site_reported_count = (
        str(name or "").startswith("count_")
        and any(phrase in boundary for phrase in (
            "displayed total", "displayed record count", "records found",
            "site-reported count", "grid's displayed total record count",
        ))
        and not re.search(r"\b(?:len|sum)\s*\(", method_code)
    )
    if ((str(name or "").startswith("count_") and not site_reported_count)
            or "count unique" in boundary):
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
            old_capability = str(old.get("capability") or "").rstrip(".")
            new_capability = str(replacement.get("capability") or "").rstrip(".")
            if not new_capability.startswith(old_capability):
                item_errors.append(
                    "UPDATE capability must preserve the old capability text as a prefix"
                )
            if not _contract_is_backward_compatible(
                old.get("input_contract") or {}, replacement.get("input_contract") or {},
                input_contract=True,
            ) or not _contract_is_backward_compatible(
                old.get("output_contract") or {}, replacement.get("output_contract") or {},
                input_contract=False,
            ):
                item_errors.append(
                    "UPDATE contract changes must be backward-compatible additive widening"
                )
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
            if decision == "COVERED" and extractions is not None:
                candidate = next((candidate for extraction in extractions
                                  for candidate in extraction.get("candidates") or []
                                  if str(candidate.get("candidate_id")) == str(attr.get("candidate_id"))), None)
                target_id = attr.get("target_id")
                target = next((operation.get("replacement") for operation in operations
                               if (operation.get("replacement") or {}).get("primitive_id") == target_id), None)
                target = target or pool.get(target_id)
                if candidate is not None and target is not None:
                    missing = sorted(
                        _semantic_output_fields(candidate.get("output_contract"))
                        - _semantic_output_fields(target.get("output_contract"))
                    )
                    if missing:
                        errors.append(
                            f"candidate_attribution[{i}] COVERED target drops extracted output "
                            f"fields {missing}; use backward-compatible UPDATE or REJECT"
                        )
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
            replacement.pop("candidate_key", None)
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
        duplicates = sorted({pid for pid in ids if ids.count(pid) > 1})
        errors.append(
            f"final primitive ids must be unique; duplicates={duplicates}. If a MERGE replacement "
            "has the same final id as a KEEP source, consume that source in the MERGE too instead "
            "of emitting both."
        )
    contract_groups = {}
    for primitive in final:
        signature = (
            str(primitive.get("feature") or ""),
            json.dumps(_schema_shape(primitive.get("input_contract")), sort_keys=True),
        )
        contract_groups.setdefault(signature, []).append(primitive.get("primitive_id"))
    for (feature, _), primitive_ids in contract_groups.items():
        if feature and len(primitive_ids) > 1:
            errors.append(
                f"overlapping {feature} primitives share the same input contract: "
                f"{primitive_ids}; merge configuration variants behind a semantic enum or "
                "make their semantic input contracts distinct"
            )
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
    *, site: str, workflows: list[dict], output: str | Path, batch_size=4, seed=20260810,
    llm_fn: Callable[[str, str], dict], max_attempts: int = 3,
    rebuild_from_batch: int | None = None, max_workers: int = 16,
) -> dict:
    """Build independent batch candidates in parallel, then consolidate their union once."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    batches = partition_workflows(workflows, batch_size=batch_size, seed=seed)
    previous_config = {}
    if (output / "config.json").exists():
        previous_config = json.loads((output / "config.json").read_text(encoding="utf-8"))
    build_mode = "parallel_initial_v1"
    can_resume_batches = (
        previous_config.get("build_mode") == build_mode
        and previous_config.get("batch_size") == batch_size
        and previous_config.get("shuffle_seed") == seed
    )
    config = {"site": site, "batch_size": batch_size, "shuffle_seed": seed,
              "group_by": "site", "order_before_shuffle": ["template_id", "task_id"],
              "build_mode": build_mode, "max_workers": max_workers,
              "batch_dependency": "frozen_empty_catalog",
              "serial_stage": "consolidation"}
    _dump(output / "config.json", config)
    _dump(output / "workflow_order.json", {
        "batches": [[{"id": x["id"], "task_id": x.get("task_id"),
                       "template_id": x.get("template_id"),
                       "task_type": x.get("task_type", "retrieve")}
                      for x in batch] for batch in batches]
    })
    history = []
    all_workflows = {str(x["id"]): x for x in workflows}
    extractions_by_workflow = {}

    def extract_one(workflow):
        directory = output / "extractions" / str(workflow["id"])
        existing_extraction = directory / "extraction.json"
        existing_validation = directory / "validation.json"
        if existing_extraction.exists() and existing_validation.exists():
            validation = json.loads(existing_validation.read_text(encoding="utf-8"))
            if validation.get("accepted") is True:
                return str(workflow["id"]), json.loads(
                    existing_extraction.read_text(encoding="utf-8")
                )
        inp = {"site": site, "workflow": workflow}
        _dump(directory / "input.json", inp)
        attempts, raw, errors = [], {}, []
        for attempt in range(1, max_attempts + 1):
            attempt_input = dict(inp)
            if errors:
                attempt_input.update({"previous_rejected_extraction": raw,
                                      "validation_feedback": errors,
                                      "retry_instruction": "Regenerate without losing demonstrated site capabilities."})
            raw = _normalize_extraction(
                llm_fn(_EXTRACT_SYS, json.dumps(attempt_input, ensure_ascii=False)) or {}
            )
            errors = validate_extraction(raw, workflow=workflow)
            attempts.append({"attempt": attempt, "proposal": raw, "errors": errors})
            if not errors:
                break
        _dump(directory / "attempts.json", attempts)
        _dump(directory / "extraction.json", raw)
        _dump(directory / "validation.json", {"accepted": not errors, "errors": errors})
        if errors:
            raise ValueError(f"{site} extraction {workflow['id']} rejected: {errors}")
        return str(workflow["id"]), raw

    worker_count = max(1, min(max_workers, len(workflows) or 1))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(extract_one, workflow) for workflow in workflows]
        for future in as_completed(futures):
            workflow_id, extraction = future.result()
            extractions_by_workflow[workflow_id] = extraction

    def build_batch(number, batch):
        directory = output / "batches" / f"batch_{number:03d}"
        validation_path = directory / "validation.json"
        snapshot_path = directory / "snapshot" / "primitive_pool.json"
        diff_path = directory / "primitive_diff.json"
        may_resume = can_resume_batches and (
            rebuild_from_batch is None or number < rebuild_from_batch
        )
        if may_resume and validation_path.exists() and snapshot_path.exists() and diff_path.exists():
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            if validation.get("accepted") is True:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                diff = json.loads(diff_path.read_text(encoding="utf-8"))
                return number, snapshot, diff, True
        frozen_pool = {}
        batch_extractions = [extractions_by_workflow[str(x["id"])] for x in batch]
        inp = {"site": site, "build_mode": "parallel_initial", "batch": batch,
               "extractions": batch_extractions, "catalog_index": [],
               "retrieved_primitives": []}
        _dump(directory / "input.json", inp)
        attempts, raw, accepted, errors = [], {}, [], []
        for attempt in range(1, max_attempts + 1):
            attempt_input = dict(inp)
            if errors:
                attempt_input["previous_rejected_proposal"] = raw
                attempt_input["validation_feedback"] = errors
                attempt_input["retry_instruction"] = (
                    "Regenerate the complete proposal rather than repeating it. Correct every "
                    "validation and quality-gate error literally, including narrowing an "
                    "over-broad primitive instead of rejecting its evidenced typed core. Do not "
                    "invent code or evidence. If completeness is not exactly 'complete', "
                    "supports_absence_proof MUST be false. If feedback says a REJECT drops an "
                    "evidenced reusable core, that candidate MUST become ADD or UPDATE in the "
                    "next proposal. If COVERED drops typed fields, widen the target with code "
                    "that parses those fields or create a separate ADD, and link every generated "
                    "operation from candidate_attribution."
                    " Mechanically audit the final candidate_attribution before returning: "
                    "each ADD/UPDATE operation index must be referenced by at least one ADD/UPDATE "
                    "candidate decision, and do not create an operation for a capability that has "
                    "no extracted candidate. When feedback says COVERED drops output fields, do "
                    "not repeat COVERED with the same lossy target: emit one richer ADD that returns "
                    "the union of demonstrated stable fields and point all matching candidates to "
                    "that operation, or REJECT only when the extraction itself has a specific "
                    "boundary/evidence defect. When workflow-level aggregation is rejected, return "
                    "the underlying typed site records and leave count/rank/selection to workflow code."
                )
            raw = _normalize_safe_guarantee_weakening(_reconcile_workflow_attribution(
                _drop_unlinked_semantic_operations(_normalize_operation_envelopes(
                    llm_fn(_BUILD_SYS, json.dumps(attempt_input, ensure_ascii=False)) or {}
                )), batch
            ))
            accepted, errors = validate_build_proposal(
                raw, site=site, batch=batch, pool=frozen_pool, all_workflows=all_workflows,
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
        local_pool, diff = apply_build_operations(frozen_pool, accepted)
        _dump(directory / "primitive_diff.json", diff)
        snapshot = list(local_pool.values())
        _dump(directory / "snapshot" / "primitive_pool.json", snapshot)
        for primitive in snapshot:
            (directory / "snapshot" / "code").mkdir(parents=True, exist_ok=True)
            (directory / "snapshot" / "code" / f"{primitive['method']}.py").write_text(
                primitive["method_code"], encoding="utf-8"
            )
        return number, snapshot, diff, False

    batch_results = {}
    worker_count = max(1, min(max_workers, len(batches) or 1))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(build_batch, number, batch)
                   for number, batch in enumerate(batches)]
        for future in as_completed(futures):
            number, snapshot, diff, resumed = future.result()
            batch_results[number] = (snapshot, diff, resumed)

    # Keep independently generated duplicates as distinct consolidation sources. The LLM must
    # consume their manager keys once; no batch wins merely because it completed first.
    pool = {}
    for number, batch in enumerate(batches):
        snapshot, diff, resumed = batch_results[number]
        history.append({"batch": number, "workflows": [x["id"] for x in batch],
                        "diff": diff, "resumed": resumed})
        for index, primitive in enumerate(snapshot):
            base_key = str(primitive["primitive_id"])
            candidate_key = base_key
            if candidate_key in pool:
                candidate_key = f"{base_key}#batch_{number:03d}_candidate_{index:03d}"
            row = deepcopy(primitive)
            row["candidate_key"] = candidate_key
            pool[candidate_key] = row

    candidate_rows = list(pool.values())
    _dump(output / "pre_consolidation" / "primitive_pool.json", candidate_rows)
    consolidation_input = {"site": site, "primitive_pool": candidate_rows}
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
        raw = _normalize_consolidation_response(
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
