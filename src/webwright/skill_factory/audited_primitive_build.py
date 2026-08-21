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
 "configuration":{"kind":"none|internal|semantic_enum","input_field":null|"field_name","supported_values":[],
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
Treat deployment endpoints, browser state, and credentials as runtime context rather than task
semantics. Resource-acquisition candidates consume that context through the component boundary and
declare any required state; they do not turn runtime plumbing into task parameters. Authentication
components return authenticated-state facts, never secret material for another public component.
Site-rendered units, locale, timezone, and status conventions are site semantics, not answer
formatting. Preserve a displayed representation when useful, but also expose an unambiguous typed
canonical field whenever the demonstrated syntax supports parsing it. Keep values with different
source semantics distinct rather than collapsing them into one ambiguous field.

Candidate-set acquisition mechanics are website operations when the site itself exposes
pagination, continuation, batch execution, or stable identity. Ordinary client-side repetition of
the same atomic acquisition over caller-chosen inputs is workflow orchestration: extract the atomic
operation once and leave input-family choice, repetition, cross-call merge/dedup, semantic filtering,
ranking, and answer formatting to the workflow. A batch candidate is distinct only when evidence
demonstrates a site-native transaction or stateful control that repeated atomic calls cannot
represent. A bounded acquisition must not claim exhaustive discovery outside its declared scope.
Generic client-side computation over acquired records is workflow logic unless the website itself
returns that value as an objective field.

Do not overfit a typed record to only the fields consumed by the current task. At the same
demonstrated acquisition boundary, preserve stable objective identity, temporal, state, value,
link, and pagination/completeness fields that the evidence actually exposes. This is not license
to invent undocumented fields. Preserve distinct identity, temporal, state, value, link, and
pagination semantics rather than collapsing richer evidence into a task-tailored projection.
For candidate/search records, identity is more than a non-empty label or coordinates. When the
same evidenced response exposes stable identity discriminators such as canonical name, entity
kind/type/category or role, parent/scope, locality, or stable ID, preserve them as separately typed
fields. Do not drop those fields merely because the source task happened to select by name; do not
invent them when the source acquisition does not expose them.
Reserve the input name `page` for the component's browser object (`self.page`). Describe numeric
pagination inputs as `page_number` in candidate input contracts.
An output is typed only when its schema gives each value a stable semantic role. Positional cells,
unscoped rendered text, or another opaque UI fragment cannot substitute for a record schema.
Text that is itself a domain fact remains valid when represented as a semantically named field.
When two evidence-supported field names express the same role, annotate their JSON-schema property
with `"semantic_role":"safe_snake_case"`; never rely on site-specific alias tables.
Do not expose an opaque serialized site parameter when its demonstrated semantic structure can be
represented and validated as typed input. Serialization order and low-level coupling remain inside
the primitive.
Preserve exact successful source selectors as evidence. Do not replace a demonstrated field name
with a guessed accessibility role or generic selector during later code generation unless another
gold workflow directly demonstrates that alternative.

A website package owns mechanisms of that website deployment. When the source tries both the
site-local endpoint/UI and unrelated external fallback providers, extract the site-local mechanism;
do not turn a workaround provider into a supported configuration of this site's primitive.
Preserve the failed/fallback attempt as provenance, not as a supported site capability. If several
source paths hit the same site acquisition and differ
only in requested fields, pagination, or projection, expose the richest evidence-supported typed
site-local boundary rather than separate lossy variants.

Guarantees describe only what the demonstrated acquisition can establish. Ranked or page-scoped
collections do not support absence proof. If site parameters are coupled, expose one semantic
choice and resolve the low-level mapping inside the primitive; never expose invalid independently
combinable controls. Acceptance checks state
observable postconditions that distinguish valid empty output from acquisition failure.
Hard invariant: `supports_absence_proof` may be true only when `completeness` is exactly
`complete`. For page-, query-, bounded-, partial-, or conditional acquisition it must be false,
even when the source workflow happened to find no matching record. Absence in one acquired slice
is not proof of site-wide absence.
`supports_absence_proof` describes an empty collection within a declared complete acquisition
scope. It is not a synonym for successfully parsing one scalar or record. Finite semantic
configuration choices must be represented as an explicit enum whose low-level mapping remains
internal to the primitive.

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
 "configuration":{"kind":"none|internal|semantic_enum","input_field":null|"field_name","supported_values":[],
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
Ordinary repetition of one site acquisition over several caller-supplied queries is workflow
orchestration, not another public primitive: the workflow calls the single-query primitive in a
loop and owns query generation/order. Only retain a batch/multi-query primitive when the site
itself exposes a distinct batch transaction or stateful control that cannot be represented as
repeated calls to the atomic primitive. Never expose parallel one-shot and Python-loop variants.
Do not REJECT such an extracted candidate merely because its one source workflow used concrete
task terms or because only one workflow demonstrates it. When those terms have
been lifted into caller inputs and task filtering/selection remains outside, preserve the evidenced
acquisition mechanism as ADD or a genuinely backward-compatible UPDATE.
Methods are generated for a feature component class whose __init__ stores `self.page`. Therefore
the canonical package runtime is async Playwright: every public method is `async def`, starts with
`self`, awaits browser/page/request calls, uses `self.page` for browser access, and MUST NOT expose
a separate browser `page` parameter. The name `page` is reserved for that browser object: API/UI
pagination inputs must be named `page_number` (and represented that way in input_contract), never
`page`. Formatting a typed fact as a final answer is workflow logic; parsing a site-rendered value
into an unambiguous typed representation is primitive logic whenever the demonstrated syntax is
parseable. Preserve the displayed representation alongside it when useful, and keep values with
different source semantics explicitly distinct.
Generated code MUST be deployment-portable. Never preserve a literal `http://host:port` or
`https://host:port` from a source workflow. Use the runtime page origin or a semantic `base_url`
input, and keep relative UI paths relative. A site-internal backend endpoint may be discovered from
the current deployment's own assets/configuration or reached through the UI; do not hard-code the
source deployment's frontend, backend, API, or port into reusable method code.
Do not "parameterize" a separately hosted backend by merely replacing its origin with the current
frontend origin while preserving its path. A backend path is coupled to the backend component;
there must be source evidence that the same path exists on the frontend origin, or generated code
must discover the current backend endpoint from this deployment's own assets/configuration. When
that evidence is absent, use the evidenced portable UI acquisition instead.
For Python Playwright navigation, a leading-slash string is not a valid portable target. Derive
`origin = f"{urlsplit(self.page.url).scheme}://{urlsplit(self.page.url).netloc}"`, then call
`urljoin(origin + "/", relative_path.lstrip("/"))` before `page.goto` or `page.request.*`.
This runtime-origin recipe is portable; neither `goto("/path")` nor a literal source host is.
When source evidence contains an exact successful selector or field name, preserve it as the
primary acquisition path. Do not replace it with a guessed role/label selector unless another
source workflow directly demonstrates that selector. Typed numeric parsing must preserve decimal
values and units (for example `8.4km`) and include a parser-level example that round-trips to the
declared normalized value; a regex that stops at a decimal point is invalid.
Do not click a page-global generic `Close` control after opening a target panel/form. Such a click
may dismiss the very acquisition UI the primitive needs. Modal cleanup is allowed only when source
evidence or behavior diagnostics identify a selector scoped to a known obstructing modal.
Semantically structured site inputs must use typed objects with explicit validation; serialize
opaque site request parameters internally rather than exposing their encoding as public input.
Do not create `count_*` primitives that compute len/count over acquired records. Return typed
records and let the workflow aggregate them. A total explicitly supplied by the website may be
returned as an objective field alongside records.
Typed record schemas should be lossless with respect to stable objective fields demonstrated at
the acquisition boundary, not minimal projections tailored to the source task. Preserve distinct
identity fields, distinct site timestamps, stable hrefs/ids/state, and explicit pagination or
enumeration-completeness metadata when supported by evidence. Never claim a collection is complete
merely because the current source task stopped after one page.
For candidate/search records, preserve every evidenced discriminator needed to distinguish
semantically adjacent records: canonical name, entity kind/type/category or role, parent/scope,
locality, and stable ID. A label plus coordinates or URL does not subsume a richer evidenced typed
identity record. The workflow still owns the current task's semantic match decision.
Hard invariant: set `supports_absence_proof` to true only when `completeness` is exactly
`complete`; otherwise set it to false. A valid empty page, query, bounded scan, or conditional
collection is not an absence proof outside that explicitly complete acquisition scope.
When input/output names differ across source workflows but represent the same evidence-supported
concept, use a JSON-schema property annotation `semantic_role` with a safe snake_case value. Do not
invent equivalence from lexical similarity.
Every replacement must state machine-readable guarantees and observable acceptance checks. A
configuration contract may be `semantic_enum` only when `input_field` names an input property with
the same explicit enum, code accepts that semantic parameter, internally maps every supported value
to coupled deployment controls, and checks the response. Other configuration kinds set
`input_field` to null.
Never expose coupled endpoint/port/profile controls as independently combinable public inputs.
Do not infer a configuration contradiction merely because a low-level path/profile label remains
constant while another coupled deployment control (such as endpoint or port) changes. When
successful source workflows demonstrate the semantic modes, hide the complete evidenced mapping
behind one semantic enum rather than exposing or interpreting its low-level pieces independently.
Do not expose unrelated external fallback services as a semantic provider enum for a site package.
Prefer the evidenced site-local endpoint or UI. A declared output field is valid only when the
generated request and parser actually acquire it.

Read operations return typed facts. Effectful operations return a typed receipt containing only
evidence-supported identifiers/state plus observable postconditions that distinguish success,
no-op, and failure. The workflow decides whether and when to perform the effect; the primitive owns
only the site's action mechanics. Never promote a failed or blocked source attempt into an
effectful capability.

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
and source attribution with a concise explanation of any generalization. `feature_assignments`
must contain one safe feature name per replacement in the same order. A replacement may omit its
redundant `feature` field; the deterministic manager copies the aligned assignment into it. If a
replacement includes `feature`, it must exactly match the aligned assignment.

Feature classes are composition components such as auth, reviews, commits, orders, or routes;
they are not inheritance subclasses. Choose cohesive site features. Preserve the primitive/workflow
boundary: site mechanics and typed parsing belong in primitives; task filtering, aggregation,
ranking, subjective decisions, and answer formatting remain in workflows. Do not alter KEEP code.
MERGE/SPLIT replacements preserve or strengthen explicit guarantees and acceptance checks. Do not
turn conflicting configuration evidence into freely combinable public parameters; use a semantic
enum with an internal mapping, or keep the capability narrower.
Never split a complete paginated acquisition into a public authentication-token primitive plus a
single-page consumer. Authentication tokens/cookies/keys remain private implementation details;
the public acquisition must keep authentication and site pagination internal and preserve the
source's complete/absence-proof mode. A SPLIT replacement must not introduce a new caller input
that was not already public on the source primitive.
MERGE overlapping acquisition primitives that address the same site resource even when their
input names, provider wrappers, or output projections differ. The replacement should keep one
site-local mechanism and the lossless union of evidence-supported objective fields. Do not KEEP
parallel acquisitions merely because one is a lossy projection or exposes an external
fallback provider. A site package must not depend on unrelated public services when an evidenced
site-local mechanism exists. Verify that every promised output field is enabled by the request
and populated by the parser; otherwise repair it in the MERGE replacement or omit the unsupported
field.
All consolidation replacements remain deployment-portable: no literal source-workflow origin or
backend host/port may survive in method code. Preserve a relative site path, derive the current
origin from the runtime page, or expose one semantic base URL input as appropriate.
Never relocate a separate backend path onto the frontend origin without evidence that the frontend
serves that path; retain a portable UI method or discover the endpoint from deployment assets.
All replacement public methods use the package's canonical async Playwright runtime: emit
`async def` and await every browser/page/request coroutine.
Consolidation must collapse an atomic primitive and any client-side loop wrapper into the atomic
primitive; workflows can call it repeatedly. Preserve exact successful source selectors as primary
paths, and preserve evidenced numeric precision and units in typed outputs.
When `behavior_smoke_feedback` is present, treat every failed probe as a release-blocking contract
counterexample. Regenerate the affected replacement from source evidence; do not explain away,
delete, or hard-code the probe. Preserve passing acquisitions while correcting the general parser,
selector, portability, or async-runtime defect demonstrated by the failure.
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
The generated package runtime is async Playwright. FAIL a synchronous public method that calls
async page/request APIs, or any browser operation whose coroutine is used without `await`.
PASS a source-evidenced atomic candidate acquisition that accepts caller-supplied semantic inputs
and returns typed site facts. FAIL a second public primitive that merely loops over that atomic
operation in client code; the workflow owns repetition and input-family choice. A batch primitive
is distinct only when the website exposes a source-evidenced transaction or stateful control that
repeated atomic calls cannot represent. Also FAIL task-category hard-coding, generic client-side
filtering/ranking/aggregation, or exhaustive claims without an evidenced completeness mechanism.
FAIL generated acquisition code that replaces a source-evidenced exact successful selector with
an unsupported guessed role, label, or generic whole-page selector. FAIL typed numeric parsing
that truncates decimal values or drops evidenced units.
FAIL a primitive that exposes an opaque serialized site parameter when the demonstrated semantic
structure can be typed and validated before request construction.
Website-specific authentication mechanics are valid primitives when evidence demonstrates the
site's login URL/form selectors, submit behavior, and authenticated-state detection. Do not reject
such a candidate as generic browser setup merely because credentials are parameters.
Effectful operations are valid only when successful source evidence demonstrates the site action
and the output contract exposes observable postconditions distinguishing success, no-op, and
failure. The workflow retains policy over whether and when to invoke the action.

FAIL a lossy task-tailored projection when the cited evidence demonstrates additional stable
objective record fields needed to interpret identity, time, state, links, or collection
completeness. FAIL an output that looks like a complete collection but neither traverses nor
reports pagination/completeness. Do not demand fields absent from the supplied evidence.
For candidate/search records, treat evidenced kind/type/category, role, parent/scope, locality,
canonical name, and stable ID as identity-bearing fields: FAIL a projection that keeps only a
label/coordinate/URL while discarding those available discriminators.
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
FAIL pseudo-portability that takes a path evidenced only on a separately hosted backend and joins
it to the current frontend origin. Passing this gate requires evidence for that same-origin path,
runtime discovery of the current backend from site assets/configuration, or use of the evidenced
portable UI acquisition. Changing only the hostname is not endpoint generalization.

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
        if fn.name == public_name and not isinstance(fn, ast.AsyncFunctionDef):
            errors.append(f"public method {fn.name} must be async def for async Playwright")
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
    def semantic_name(name, schema):
        role = schema.get("semantic_role") if isinstance(schema, dict) else None
        return role if isinstance(role, str) and _SAFE.fullmatch(role) else name
    # These are private authentication mechanics, not reusable semantic outputs.  They may be
    # acquired and consumed inside a primitive, but must not force a public contract to expose
    # credentials/tokens merely because a source workflow kept them in a local variable.
    internal_auth_fields = {
        "form_key", "csrf_token", "csrfmiddlewaretoken", "xsrf_token",
        "session_cookie", "session_cookies", "access_token", "bearer_token",
    }
    ignored = {"type", "items", "properties", "fields", "required", "description", "enum",
               "default", "anyOf", "oneOf", "allOf", "format", "nullable",
               "semantic_role"}
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
                        fields.add(semantic_name(name, child))
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
                    fields.add(semantic_name(name, child))
                fields.update(_semantic_output_fields(child))
            elif name in {"items", "anyOf", "oneOf", "allOf"}:
                fields.update(_semantic_output_fields(child))
    elif isinstance(value, list):
        for child in value:
            fields.update(_semantic_output_fields(child))
    return {
        name for name in fields
        if not name.startswith("raw_") and not name.endswith("_path")
    }


def _required_semantic_output_fields(value) -> set[str]:
    """Collect only contractually required facts, retaining legacy compact schemas.

    JSON-schema properties not named in ``required`` are optional observations.  A COVERED
    attribution may omit those observations without violating the extracted contract.  Older
    compact schemas have no ``required`` vocabulary, so all of their declared fields remain
    required for backward-compatible coverage.
    """
    def project(node):
        if isinstance(node, list):
            return [project(child) for child in node]
        if not isinstance(node, dict):
            return node
        result = {}
        for key, child in node.items():
            if key in {"properties", "fields"} and isinstance(child, dict):
                declared = node.get("required")
                names = set(declared) if isinstance(declared, list) else set(child)
                result[key] = {
                    name: project(schema) for name, schema in child.items() if name in names
                }
            elif key != "required":
                result[key] = project(child)
        return result

    return _semantic_output_fields(project(value))


def _contract_leaf_fields(value) -> set[str]:
    """Collect public leaf field names without applying output-only ignore rules."""
    def semantic_name(name, schema):
        role = schema.get("semantic_role") if isinstance(schema, dict) else None
        return role if isinstance(role, str) and _SAFE.fullmatch(role) else name

    schema_keys = {
        "type", "items", "properties", "fields", "required", "description", "enum",
        "default", "anyOf", "oneOf", "allOf", "format", "nullable", "minItems",
        "maxItems", "minimum", "maximum", "minLength", "maxLength", "pattern",
        "semantic_role",
    }
    fields = set()
    if isinstance(value, dict):
        for container in ("properties", "fields"):
            children = value.get(container)
            if isinstance(children, dict):
                for name, child in children.items():
                    structured = isinstance(child, (dict, list)) and (
                        isinstance(child, list)
                        or any(key in child for key in ("properties", "fields", "items",
                                                        "anyOf", "oneOf", "allOf"))
                    )
                    if not structured:
                        fields.add(semantic_name(name, child))
                    fields.update(_contract_leaf_fields(child))
        for name, child in value.items():
            if name not in schema_keys and name not in {"properties", "fields"}:
                structured = isinstance(child, (dict, list)) and (
                    isinstance(child, list)
                    or any(key in child for key in ("properties", "fields", "items",
                                                    "anyOf", "oneOf", "allOf"))
                )
                if not structured:
                    fields.add(semantic_name(name, child))
                fields.update(_contract_leaf_fields(child))
            elif name in {"items", "anyOf", "oneOf", "allOf"}:
                fields.update(_contract_leaf_fields(child))
    elif isinstance(value, list):
        for child in value:
            fields.update(_contract_leaf_fields(child))
    return fields


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
        config_required = {
            "kind", "input_field", "supported_values", "coupled_site_parameters_hidden",
        }
        if set(configuration) != config_required:
            errors.append(f"guarantees.configuration keys must be exactly {sorted(config_required)}")
        kind = configuration.get("kind")
        input_field = configuration.get("input_field")
        values = configuration.get("supported_values")
        if kind not in {"none", "internal", "semantic_enum"}:
            errors.append("guarantees.configuration.kind is invalid")
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            errors.append("guarantees.configuration.supported_values must be strings")
        elif kind == "semantic_enum" and not values:
            errors.append("semantic_enum configuration requires supported_values")
        properties = (value.get("input_contract") or {}).get("properties") or {}
        if kind == "semantic_enum":
            if not isinstance(input_field, str) or input_field not in properties:
                errors.append(
                    "semantic_enum configuration requires input_field naming an input property"
                )
            else:
                field_values = properties[input_field].get("enum") if isinstance(
                    properties[input_field], dict
                ) else None
                if not isinstance(field_values, list) or not field_values:
                    errors.append("semantic_enum input_field requires an explicit enum")
                elif set(values or []) != {str(item) for item in field_values}:
                    errors.append(
                        "guarantees supported_values must match the configured input enum"
                    )
        elif input_field is not None:
            errors.append("non-semantic configuration must set input_field to null")
        if kind in {"none", "internal"} and values:
            errors.append("non-semantic configuration must not declare supported_values")
        if configuration.get("coupled_site_parameters_hidden") is not True:
            errors.append("coupled site parameters must be hidden")
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

    _, code_errors = _parse_methods(str(value.get("method_code") or ""), str(name or ""))
    errors.extend(code_errors)
    output = _norm(_schema_shape(value.get("output_contract"))).lower()
    if any(term in output for term in ("locator", "elementhandle", "raw dom", "raw_html",
                                       "raw html", "untyped text", "page text")):
        errors.append("output_contract exposes raw/untyped site output")
    output_fields = _semantic_output_fields(value.get("output_contract") or {})
    public_output_fields = {
        field.lower() for field in _contract_leaf_fields(value.get("output_contract") or {})
    }
    private_output_fields = {
        field for field in public_output_fields
        if (
            field in {"token", "password", "secret", "cookie", "cookies", "form_key"}
            or field.endswith(("_token", "_password", "_secret", "_cookie", "_cookies"))
        ) and not field.endswith(("_present", "_observed"))
    }
    if private_output_fields:
        errors.append(
            "output_contract exposes private authentication material: "
            + ", ".join(sorted(private_output_fields))
        )
    if "duration_text" in output_fields and "duration_seconds" not in output_fields:
        errors.append("duration_text requires typed duration_seconds in the output contract")
    boundary = _norm({"method": name, "capability": value.get("capability"),
                      "owns": value.get("owns")}).lower()
    if str(name or "").startswith("format_") or "final answer formatting" in boundary or (
        "format duration" in boundary and "parse" not in boundary
    ):
        errors.append("primitive owns workflow-level formatting rather than site-specific parsing")
    method_code = str(value.get("method_code") or "")
    if re.search(r"https?://[A-Za-z0-9]", method_code):
        errors.append("method_code hard-codes a deployment origin; derive it from runtime context")
    if re.search(r"self\.page\.(?:goto|request\.(?:get|post|put|delete))\(\s*f?['\"]/", method_code):
        errors.append(
            "Playwright navigation/request uses a relative absolute-path string; resolve it "
            "against the current page origin before calling the Python API"
        )
    if ".raise_for_status(" in method_code:
        errors.append(
            "Playwright APIResponse has no raise_for_status(); check response.ok/status and "
            "raise an explicit acquisition error"
        )
    if re.search(
        r"(?:self\.)?page\.get_by_role\(\s*['\"]button['\"]\s*,\s*name\s*=\s*['\"]Close['\"]",
        method_code,
    ):
        errors.append(
            "method_code uses a page-global generic Close control; scope modal cleanup to a "
            "source-evidenced obstructing container or omit it"
        )
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
                        _required_semantic_output_fields(candidate.get("output_contract"))
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
            assignments = op.get("feature_assignments")
            if assignments is not None:
                if not isinstance(assignments, list) or len(assignments) != len(replacements):
                    errors.append(
                        f"operations[{i}] SPLIT feature_assignments must align one-to-one "
                        "with replacements"
                    )
                else:
                    for j, (replacement, assignment) in enumerate(
                        zip(replacements, assignments)
                    ):
                        explicit = replacement.get("feature")
                        if explicit in {None, ""}:
                            replacement["feature"] = assignment
                        elif explicit != assignment:
                            errors.append(
                                f"operations[{i}].replacements[{j}] feature {explicit!r} "
                                f"conflicts with feature_assignments value {assignment!r}"
                            )
        else:
            errors.append(f"operations[{i}] unknown op {kind!r}")
            continue
        for j, replacement in enumerate(replacements):
            item_errors = validate_primitive(
                replacement, site=site, workflows=workflows, classified=True
            )
            errors.extend(f"operations[{i}].replacements[{j}]: {x}" for x in item_errors)
            final.append(replacement)
        if kind == "MERGE" and sources and all(source in pool for source in sources):
            source_inputs = set().union(*(
                _contract_leaf_fields(pool[source].get("input_contract") or {})
                for source in sources
            ))
            replacement_inputs = _contract_leaf_fields(
                replacement.get("input_contract") or {}
            )
            missing_inputs = sorted(source_inputs - replacement_inputs)
            if missing_inputs:
                errors.append(
                    f"operations[{i}] MERGE drops source input modes {missing_inputs}; "
                    "preserve them in one semantic contract or keep capabilities separate"
                )
            source_outputs = set().union(*(
                _semantic_output_fields(pool[source].get("output_contract") or {})
                for source in sources
            ))
            replacement_outputs = _semantic_output_fields(
                replacement.get("output_contract") or {}
            )
            missing_outputs = sorted(source_outputs - replacement_outputs)
            if missing_outputs:
                errors.append(
                    f"operations[{i}] MERGE drops source output facts {missing_outputs}; "
                    "preserve the lossless typed union"
                )
        elif kind == "SPLIT" and source in pool and replacements:
            source_input_fields = _contract_leaf_fields(pool[source].get("input_contract") or {})
            introduced_inputs = set().union(*(
                _contract_leaf_fields(item.get("input_contract") or {})
                for item in replacements
            )) - source_input_fields
            introduced_private_inputs = sorted(
                field for field in introduced_inputs
                if field.lower() in {
                    "token", "bearer_token", "access_token", "csrf_token", "xsrf_token",
                    "form_key", "cookie", "cookies", "session_cookie", "session_cookies",
                    "password", "secret",
                } or field.lower().endswith(("_token", "_cookie", "_cookies", "_secret"))
            )
            if introduced_private_inputs:
                errors.append(
                    f"operations[{i}] SPLIT introduces private intermediate public inputs "
                    f"{introduced_private_inputs}; "
                    "keep intermediate authentication/configuration inside a standalone primitive"
                )
            replacement_inputs = set().union(*(
                _contract_leaf_fields(item.get("input_contract") or {})
                for item in replacements
            ))
            missing_inputs = sorted(
                _contract_leaf_fields(pool[source].get("input_contract") or {})
                - replacement_inputs
            )
            if missing_inputs:
                errors.append(
                    f"operations[{i}] SPLIT drops source input modes {missing_inputs}"
                )
            replacement_outputs = set().union(*(
                _semantic_output_fields(item.get("output_contract") or {})
                for item in replacements
            ))
            missing_outputs = sorted(
                _semantic_output_fields(pool[source].get("output_contract") or {})
                - replacement_outputs
            )
            if missing_outputs:
                errors.append(
                    f"operations[{i}] SPLIT drops source output facts {missing_outputs}"
                )
            source_guarantees = pool[source].get("guarantees") or {}
            source_required_outputs = _required_semantic_output_fields(
                pool[source].get("output_contract") or {}
            )
            complete_replacements = [
                item for item in replacements
                if (item.get("guarantees") or {}).get("completeness") == "complete"
                and source_required_outputs <= _semantic_output_fields(
                    item.get("output_contract") or {}
                )
            ]
            if source_guarantees.get("completeness") == "complete" and not complete_replacements:
                errors.append(
                    f"operations[{i}] SPLIT downgrades a complete source acquisition; at least "
                    "one standalone replacement covering its required facts must remain complete"
                )
            if source_guarantees.get("supports_absence_proof") is True and not any(
                (item.get("guarantees") or {}).get("supports_absence_proof") is True
                for item in complete_replacements
            ):
                errors.append(
                    f"operations[{i}] SPLIT drops the source absence-proof capability"
                )
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
    behavior_smoke_feedback: dict | None = None,
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

    def resume_rejected_attempts(directory, *, enabled):
        """Load historical attempts so current validators can re-audit old accepted output."""
        attempts_path = directory / "attempts.json"
        validation_path = directory / "validation.json"
        if not enabled or not attempts_path.exists() or not validation_path.exists():
            return [], {}, []
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        attempts = json.loads(attempts_path.read_text(encoding="utf-8"))
        if not isinstance(attempts, list) or not attempts:
            return [], {}, []
        last = attempts[-1] if isinstance(attempts[-1], dict) else {}
        return attempts, last.get("proposal") or {}, list(validation.get("errors") or [])

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
        attempts, raw, errors = resume_rejected_attempts(directory, enabled=may_resume)
        accepted = []
        for attempt in range(len(attempts) + 1, max_attempts + 1):
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
                    "the underlying typed site records and leave count/rank/selection to workflow code. "
                    "When quality feedback identifies overlapping or lossy duplicate operations, "
                    "emit one richest evidence-supported primitive and point every subsumed candidate "
                    "at that single operation; do not keep a narrower retry/fallback duplicate. "
                    "Mechanically compare each method's returned top-level keys and nesting against "
                    "its output_contract before responding: they must have exactly the same shape. "
                    "For one acquisition role, do not emit parallel public methods merely because "
                    "source workflows used different input forms. Prefer one evidence-supported "
                    "semantic method with explicit input modes and an internal mapping; if the "
                    "evidence cannot support that union, keep only the narrower reusable core and "
                    "mark the non-subsumed candidate REJECT with a specific boundary reason. "
                    "When fixing portability, use the one allowed Python Playwright recipe: parse "
                    "scheme/netloc from self.page.url and urljoin that origin with the relative UI "
                    "path before goto/request. Never alternate between a leading-slash goto and a "
                    "literal source host. "
                    "Represent valid empty/no-match outcomes separately from acquisition or parser "
                    "failure whenever the evidence supports that distinction."
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
    if behavior_smoke_feedback:
        consolidation_input["behavior_smoke_feedback"] = behavior_smoke_feedback
    consolidation_dir = output / "consolidation"
    previous_input_path = consolidation_dir / "input.json"
    previous_input = None
    if previous_input_path.exists():
        try:
            previous_input = json.loads(previous_input_path.read_text(encoding="utf-8"))
        except Exception:
            previous_input = None
    _dump(previous_input_path, consolidation_input)
    attempts, raw, errors = resume_rejected_attempts(
        consolidation_dir, enabled=previous_input == consolidation_input
    )
    final, coverage = [], {}
    revalidated_from_attempt = None
    if attempts:
        latest_revalidation = None
        for previous in reversed(attempts):
            proposal = previous.get("proposal") if isinstance(previous, dict) else None
            if not isinstance(proposal, dict):
                continue
            candidate_final, candidate_errors, candidate_coverage = validate_consolidation(
                proposal, site=site, pool=pool, workflows=all_workflows
            )
            if latest_revalidation is None:
                latest_revalidation = (
                    proposal, candidate_errors, candidate_coverage,
                )
            if not candidate_errors:
                raw, final, errors, coverage = (
                    proposal, candidate_final, [], candidate_coverage
                )
                revalidated_from_attempt = previous.get("attempt")
                break
        if revalidated_from_attempt is None and latest_revalidation is not None:
            raw, errors, coverage = latest_revalidation
    for attempt in range(len(attempts) + 1, max_attempts + 1):
        if revalidated_from_attempt is not None:
            break
        attempt_input = dict(consolidation_input)
        if errors:
            attempt_input["previous_rejected_proposal"] = raw
            attempt_input["validation_feedback"] = errors
            attempt_input["retry_instruction"] = (
                "Regenerate the complete consolidation. Correct coverage, boundary, code, and "
                "evidence errors without silently deleting a primitive. Every SPLIT replacement "
                "must be a complete primitive with a safe feature and primitive_id exactly "
                "<site>/<feature>/<method>. Remove every page-global generic Close click; do not "
                "rename or wrap it. Preserve all passing behavior probes while repairing failures."
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
    _dump(consolidation_dir / "attempts.json", attempts)
    _dump(consolidation_dir / "proposal.json", raw)
    _dump(consolidation_dir / "validation.json", {
        "accepted": not errors, "errors": errors,
        "revalidated_from_attempt": revalidated_from_attempt,
    })
    _dump(consolidation_dir / "coverage.json", coverage)
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
