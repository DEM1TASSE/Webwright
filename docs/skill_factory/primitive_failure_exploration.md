# Primitive Failure Exploration

This is a development notebook, not a formal effectiveness evaluation. Existing scratch/oracle
runs are used as probes for primitive boundaries, contracts, retrieval, and instrumentation.

## 1. Route tasks: three distinct responsibilities

### Observations

- Tasks 52/54: scratch used a public OSRM URL with a nominal `foot` profile and returned driving-
  like durations. Oracle injection anchored the agent on the WebArena directions UI and selected
  `Foot (OSRM)`, producing correct answers.
- Task 151: the oracle workflow retained and called an adapted `route_between`, but changed its
  implementation to the deployment's OSRM HTTP endpoint. It was correct and cheaper than scratch.
- Task 152: the oracle workflow used the UI, observed `Distance: 2.7km. Time: 0:04.`, then parsed
  `0:04` as 4 seconds. The site means H:MM, so the correct normalized value is 240 seconds.

### Design implication

The current primitive mixes or omits three responsibilities:

```text
route strategy       UI engine vs deployment HTTP endpoint
site parsing         OSM `Time: H:MM`, distance units, no-route state
task presentation    HH:MM:SS, threshold comparison, requested output shape
```

Site parsing belongs inside the primitive contract. Task presentation stays in the workflow.
Strategy should be explicit rather than accidentally anchored by example code.

Proposed contract:

```python
RouteResult = {
    "duration_seconds": int,
    "distance_meters": float,
    "resolved_start": str,
    "resolved_end": str,
    "backend": "ui_osrm" | "http_osrm",
}

get_route(start, end, mode, *, backend="auto") -> RouteResult
```

The primitive may support multiple backends behind the same typed result. `backend="auto"` can
prefer a known deployment endpoint and fall back to the UI, but must report which path ran.

## 2. Zip-code tasks: entity resolution and benchmark drift

Tasks 70/71 are not clean evidence that `search_place` needs a better selector:

- Current public Nominatim returns Carnegie Mellon University's university relation with postcode
  `15232`, while the benchmark expects `15213`.
- The recorded WebArena UI for Chatham exposed results with `15217` and `15208`; current public
  Nominatim returns `15232`, which is the benchmark answer.

The benchmark gold, deployed snapshot, and current external service are not temporally aligned.
A primitive cannot infer the benchmark's preferred postcode from the observed site without
memorizing external canonical knowledge.

Principle:

> Separate primitive failures from environment/gold drift before using a task as a design probe.

`resolve_place` still needs a typed contract and should preserve alternatives:

```python
Place = {
    "name": str,
    "category": str,
    "type": str,
    "address": {
        "house_number": str | None,
        "street": str | None,
        "city": str | None,
        "state": str | None,
        "postcode": str | None,
    },
    "latitude": float,
    "longitude": float,
    "osm_type": str,
    "osm_id": int,
}

resolve_places(query, *, expected_type=None) -> list[Place]
```

Choosing among genuinely ambiguous campuses may remain task logic. The primitive should not hide
ambiguity by silently returning the first result.

## 3. Nearest-place tasks: candidate discovery is a separate capability

### Task 98

Both arms ranked their retrieved candidates correctly, but neither candidate query recalled the
gold POI `Fuku Tea`. Queries such as `tea cafe pittsburgh` and `tea house pittsburgh` returned
lexical matches such as Asia Tea House; `Fuku Tea` is tagged as a cafe but does not contain
`cafe/house` in its name.

This is a candidate-recall failure, not a route-ranking failure.

A direct development probe confirmed the missing rule:

- Nominatim query `cafe near University of Pittsburgh` recalls `Fuku Tea`.
- Routing from the resolved university to that result through the deployment's walking OSRM
  endpoint returns `653.4m`, matching the benchmark's `653m`.

So the useful site/search knowledge is to preserve both the category and origin in a contextual
discovery query. Generating only lexical category synonyms loses candidates whose names do not
contain those words.

### Task 100

The oracle workflow found the gold Starbucks and correct `557m`, but returned `location` as one
display-name string. The evaluator expected a structured location object with name, house number,
street, city, state, and postcode. This is primarily final schema noncompliance, although a typed
`Place` contract would make the correct formatting easier.

### Design implication

Do not overload `search_place(query)` to mean category discovery:

```text
resolve_places(name query)          exact/fuzzy named entity lookup
discover_nearby(origin, category)   spatial/category candidate recall
rank_by_route(origin, candidates)   route-based ranking
```

Candidate discovery should query OSM category/tag semantics or a bounded viewport, not only names.
It should return typed `Place` records; route ranking consumes those records and returns typed
distance/duration fields.

## 4. Primitive taxonomy emerging from the cases

The useful units are not arbitrary helper functions:

1. **Resolver**: user text → typed site entity candidates.
2. **Discoverer**: category + region/viewport → typed candidate set.
3. **Operator**: typed entities + mode → typed site result.
4. **Parser/normalizer**: site representation → canonical units; normally private inside an
   operator rather than independently retrieved.

Task-specific filter, aggregation, comparison threshold, and final benchmark formatting remain in
the workflow.

## 5. Instrumentation needs semantic events

A source marker answers only “was source material copied?” An entrypoint trace answers “was the
vendored function called?” Neither fully answers whether the original strategy survived adaptation:
task 151 called `route_between` but changed its backend from UI to HTTP.

Minimum useful runtime events:

```json
{"event":"primitive_enter","primitive_id":"map/get_route","hash":"..."}
{"event":"strategy","primitive_id":"map/get_route","backend":"http_osrm"}
{"event":"primitive_exit","primitive_id":"map/get_route",
 "result_shape":{"duration_seconds":"int","distance_meters":"float"}}
```

The workflow should write these to a JSONL trace under `WORKSPACE_DIR`. This separates:

```text
retrieved → copied → called → strategy selected → typed result produced
```

## 6. Pipeline principles

1. Extract stable site semantics, not merely repeated code.
2. Put site units and DOM/API parsing behind typed contracts.
3. Preserve ambiguity at the primitive boundary; do not silently choose the first entity.
4. Keep strategy explicit and observable when multiple backends exist.
5. Retrieve by missing capability (`discover candidates`, `route rank`), not only lexical task
   similarity.
6. Treat negative transfer as a contract/routing diagnostic, not just an aggregate Loss.
7. Exclude environment/gold drift cases from design conclusions.
8. Require the final workflow to validate its output against the task's declared schema.

## 7. Next minimal development experiments

1. Replace `route_between -> Locator` with typed `get_route -> RouteResult`, instrument backend,
   and rerun 151/152.
2. Add `discover_nearby` with category-aware recall; test whether it includes Fuku Tea before
   spending an agent run on task 98.
3. Feed a typed `Place` into task 100 and verify schema-shaped output.
4. Keep 70/71 as drift diagnostics, not primitive-quality probes, until the deployed data and
   benchmark gold are reconciled.

## 8. A→B consumption probe: task 54 → task 152

The first proposed experiment was run:

```text
A = task 54, template 68
    successful walking-route UI workflow
    ↓ extract/refine
map/get_route
    typed RouteResult + OSM H:MM parsing + runtime trace
    ↓ retrieve and fully inject
B = task 152, template 36
    driving-route task that failed with the old Locator contract
```

The new primitive exposed this contract during retrieval:

```text
inputs: start, end, walking|driving
output: duration_seconds, distance_meters, resolved endpoints, backend
```

The consumer copied and directly called `await get_route(...)`. Runtime trace proved:

```json
{"event":"enter","backend":"ui_osrm","mode":"driving"}
{"event":"exit","result":{"duration_seconds":240,"distance_meters":2700.0,
                          "backend":"ui_osrm"}}
```

The workflow formatted canonical `240` seconds as `00:04:00`; WebArena
`AgentResponseEvaluator` scored it **1.0**. The old primitive consumer had returned `00:00:04`
and scored 0.

Development conclusion:

> Moving stable site representation semantics across the primitive boundary fixed the observed
> cross-template consumer failure. Typed contracts also made exact execution and strategy
> attribution straightforward.

Artifacts:

- Primitive: `evals/webarena/dev_ab_library/.primitives/map/code/get_route.py`
- Result: `evals/webarena/primitive_ab_results/task152_oracle.json`
- Runtime trajectory: referenced by `run_dir` in the result record.

## 9. Multi-domain A→B probes

These are development probes for learning the abstraction boundary, not a formal comparison.
The primitives were manually refined from successful source behavior, retrieval was oracle, and
the sample was chosen for diagnostic value.

| Domain | Source A → consumer B | Relation | Result | Main observation |
|---|---|---|---|---|
| Map | 54/t68 → 152/t36 | cross-template | fail → pass | Site-specific `H:MM` parsing belongs inside a typed route contract. |
| Shopping Admin | 214/t249 → 217/t249 | same-template | fail → pass | Product alias resolution and review extraction transferred; task rating filtering remained outside. |
| GitLab | 305/t321 → 135/t322 | cross-template | fail → pass | Typed commit records were insufficient until the composer also received the task's output schema. |
| Shopping | 25/t222 and 163/t136 → 384/t666 | cross-template | pass → fail versus scratch | Correct review records anchored a broader, wrong interpretation of “complain about quality.” |

### 9.1 Shopping Admin: useful incorporation is not necessarily a function call

The consumer returned the two expected reviews in 19 steps. It retained the primitive provenance
marker and reused its product-alias broadening idea, but rewrote the implementation around the
storefront GraphQL and review endpoints instead of calling the injected entrypoint.

This is successful **adaptation**, not execution-reached. Instrumentation must distinguish:

```text
retrieved → incorporated knowledge/code → called entrypoint
```

Markers and declared usage cannot establish the last edge.

### 9.2 GitLab: there are two independent contracts

`git_clone_log` correctly produced one canonical commit record for the requested time window.
The first consumer still failed by returning per-author objects instead of the evaluator's
`[count]` shape. After the prompt exposed the task `results_schema`, the same primitive produced
`[1]`, scored 1.0, and emitted entry/exit runtime traces.

The pipeline therefore has two boundaries:

```text
website → primitive contract → canonical records
canonical records + task specification → task output contract
```

Typed primitives do not replace the task output schema; the composer needs both.

### 9.3 Shopping: a correct primitive can cause negative transfer

`get_page_reviews` retrieved ten correctly typed reviews. The consumer nevertheless added
`Misba009`, interpreting “only bad thing ... oily ... made of plastic” as a complaint about
quality. Scratch used a narrower defect/durability interpretation and returned the benchmark's
four expected names. The primitive arm took 19 steps versus 15 for scratch.

The failure is downstream of the primitive contract. Subjective concepts such as sentiment,
relevance, “quality,” or “similar” should not be silently frozen into a site primitive. They
remain task/workflow logic unless the benchmark supplies an explicit policy.

The trace also recorded several exploratory calls before the final execution. Future events need
a `phase` or execution identifier so exploration is not mistaken for final-path use.

### 9.4 Prompt-only boundary instruction did not fix the Shopping loss

A follow-up run added a domain-independent composer rule: primitives are objective evidence;
subjective categories must be derived from the current goal and must not be broadened from general
negativity or loose relatedness. The run still scored 0. It returned six names rather than the
expected four (the prior primitive run returned five), although steps fell from 19 to 14.

The generated workflow explicitly kept classification outside the primitive, but invented a
keyword policy containing `made of plastic`, `imperfections`, and `holds up`. Thus structural
separation was obeyed while semantic calibration remained wrong.

This distinguishes two claims:

1. **Layer ownership** can be stated generically: subjective classification belongs to workflow.
2. **The classification policy itself** cannot be recovered from that ownership rule when the
   task wording is underspecified.

The missing information should not be placed in a site primitive. It may come from a same-template
workflow, task examples, an explicit benchmark policy, or a conservative/abstaining classifier.
This is evidence for retaining both retrieval levels: primitive retrieval supplies site facts;
workflow retrieval supplies template-level interpretation.

Two further composer refinements isolated the remaining failure:

- A precision-first rule plus inclusion/exclusion criteria reduced the output from six names to
  five, but still included `MH`.
- Inspection showed the model's pre-code reasoning had already selected the correct four names.
  The generated classifier then added a broad `imperfections` keyword and contradicted that plan.
- Requiring record-level decisions and a planned-versus-executed set check returned exactly the
  expected four names, scored 1.0, and used 17 steps.

This successful retry fixes a **semantic-plan compilation** error, not the primitive itself. It is
also only one case: the generated workflow materialized the planned set after inspecting current
records, so this mechanism must be tested on other instances before becoming a general policy.

## 10. Refined design principles

1. A primitive captures deterministic, reusable site semantics and returns canonical typed data.
2. Parsing site units, aliases, pagination, and stable API/DOM conventions belongs inside it.
3. Subjective filtering, aggregation, and benchmark-specific formatting stays in the workflow.
4. Retrieval uses compact metadata (intent, signature, requires/provides, output shape); selected
   primitives are then injected in full.
5. The composer receives both primitive contracts and the task's required result schema.
6. `requires/provides` describe runtime state, not source-code imports. An unmet requirement is a
   useful signal that another capability may be missing.
7. Consumer failures refine the abstraction boundary: source repetition alone cannot determine
   the right primitive.
8. A correct primitive may still hurt through strategy anchoring or extra work, so routing must
   permit scratch/skip and report cost as well as correctness.
9. Same-template and cross-template results should be reported separately while using one shared
   library.
10. A prompt can enforce layer ownership but cannot manufacture an underspecified semantic policy;
    retrieve a workflow prior when template-level interpretation is the missing capability.
11. For subjective filters, preserve record-level decisions through code generation and check that
    the executed output matches the semantic plan; approximate keyword compilation is a distinct
    failure mode.

## 11. Next implementation slice

Keep the MVP vendored and non-executable:

1. Make task `results_schema` a first-class composer input.
2. Add signatures and typed output summaries to retrieval metadata; inject full code only after
   selection.
3. Record distinct retrieval, incorporation, entrypoint-call, strategy, and typed-exit events.
4. Add an execution phase/id to traces.
5. Use these four domain cases as regression fixtures for the meta-capability, while reserving a
   disjoint task set for the later formal evaluation.

Do not add shared imports, primitive dependencies, replay, or automatic version migration in this
development slice. Those remain release-stage gates.

## 12. Additional cross-template case studies

Three diagnostic pairs were run with the refined composer prompt.

| Task | Capability shape | Scratch | Primitive arm | Interpretation |
|---|---|---|---|---|
| Shopping 225/t135 | find product → reviews → objective rating filter | correct `NOT_FOUND_ERROR`, 23 steps | same answer, 20 steps, primitive incorporated | Both score 1.0 with current upstream evaluator; primitive saves 3 steps in this single run. |
| Admin 243/t244 | product reviews → “most unhappy” → customer email | no answer in 23 steps | see retrieval ablation below | The existing primitive ends at reviews; the task additionally needs a reviewer-to-customer join. |
| GitLab 308/t323 | commit records → top contributor → requested identity field | `shawn.allen`, 14 steps | same answer, 21 steps, primitive incorporated | Intent requests username while gold expects `shawn.allen@github.com`; this is task/gold semantic inconsistency. |

### 12.1 Correct-empty tasks can be invalid evaluator cases

Both task 225 arms wrote exactly the configured expected response:

```json
{"task_type":"RETRIEVE","status":"NOT_FOUND_ERROR",
 "retrieved_data":null,"error_details":null}
```

The locally checked-out evaluator raised
`Expected retrieved_data must be set in config for retrieve tasks` and assigned 0. Upstream fixed
this in commit `c7449d8`: expected and actual `None` now compare successfully, while unexpected data
still fails. Rescoring the unchanged artifacts with fetched `origin/main` gives 1.0 to both arms.

This was local evaluator staleness, not a dataset, primitive, or composer failure. Evaluation
artifacts must record the evaluator commit, and formal runs must pin a revision containing the null
expected-data fix.

### 12.2 Typed records preserve identity choices but cannot resolve a contradictory task

For task 308, `get_commits` preserved both `author_name` and `author_email`. Both agents deliberately
returned the email local-part because the intent explicitly requested username. The benchmark gold
is the full email address. Primitive injection added seven steps but could not repair a mismatch
between natural-language intent and expected output.

This case should be tagged task/gold drift. It also suggests contracts should name identity fields
precisely (`author_name`, `author_email`, `gitlab_username`) rather than expose a generic
`username`.

### 12.3 Retrieval recall and contract completeness are separate gates

Initially task 243 succeeded in 15 steps but retrieved no primitive: keyword ranking did not connect
“most unhappy” with product reviews. Adding only metadata aliases (`unhappy customer`,
`lowest-rated review`, `worst product review`) made retrieval select
`shopping_admin/get_product_reviews`.

The selected run then spent 30 steps and failed without incorporating the primitive. The primitive
returns review title/rating/body/detail URL, while the requested output requires customer email.
The consumer still had to discover a stable `review → registered customer` join and became anchored
on the incomplete material.

Therefore retrieval needs two checks:

```text
semantic relevance: can this primitive help?
contract coverage: does its provides/output advance the actual missing capability enough?
```

Lexical aliases fix the first but can worsen behavior when the second is absent. A better route is
to expose the gap explicitly:

```text
get_product_reviews          provides typed_product_reviews
resolve_review_customer      requires typed_product_review
                             provides customer_identity
```

Until the second capability exists, the router should label the first as partial evidence rather
than presenting it as a sufficient plan.

## 13. Pre-pilot fixes and regression gate

Before scaling the experiment:

1. `webarena-verified` was updated from detached `d88ef07` to `6473f72`, which contains the
   null-expected-data fix `c7449d8`.
2. The harness now records evaluator module path, commit, and fix ancestry, and refuses a known
   pre-fix evaluator instead of silently assigning invalid zeroes.
3. `primitive_usage.json` now supports a validated coverage assessment:
   `covered`, `remaining`, and `full|partial|none`.
4. The composer asks for uncovered capabilities before adaptation. Record-level decision tables
   are required only for subjective classification, not objective filters or aggregation.

Regression results:

| Task | Result | Coverage observation |
|---|---|---|
| Shopping 225 | 1.0, 20 steps | Partial: review extraction covered; product discovery, rating filter, and output remain. |
| Shopping 384 | 1.0, 25 steps | Partial: review extraction covered; product discovery and semantic classification remain. |
| Admin 243 | no answer, 19 steps | No incorporation or coverage artifact; prompt-level gap awareness did not solve the missing reviewer-to-customer join. |

The first two gates pass. The third shows that declaring partial coverage after injection is too
late to prevent distraction. Automatic routing needs a pre-injection coverage decision, or the
missing `resolve_review_customer` capability must be added. Oracle experiments may still include
this task deliberately as a partial-contract negative case, but it must not be interpreted as a
test of a complete primitive chain.

## 14. Generated-only oracle pilot

The first generated pilot used no handwritten primitive. Clean gold sources were:

```text
task 25 / template 222
task 163 / template 136
task 384 / template 666
```

All source records scored 1.0 and declared no retrieved primitive. The updater initially exposed
several structured-output robustness issues (missing `op`, nested candidates, top-level candidate,
`operation` alias). These were fixed as parser/schema compatibility only; candidate code and
provenance were never authored or repaired manually. Missing provenance and malformed IDs continued
to be rejected by the existing admission gates.

The admitted generated primitive was:

```text
shopping/parse_magento_review_list_html
provenance: task25/t222 + task384/t666
hash: sha256:3160b3b7fcd2f5eceaaf6190470a194097518d0705d402620c48073fc5fbde29
```

Held-out results:

| Task | Scratch | Forced generated oracle | Effect |
|---|---:|---:|---|
| 225/t135 | 1.0, 32 steps | 1.0, 26 steps | Tie, 6 fewer steps; primitive not copied, assessed unnecessary after empty review HTML. |
| 376/t182 | 1.0, 31 steps | 0.0, 67 steps | Loss; partial review parser anchored a long search and final status was `SUCCESS` with null instead of `NOT_FOUND_ERROR`. |
| 386/t1355 | 1.0, 10 steps | 1.0, 11 steps | Healthy skip; aggregate rating made review parsing unnecessary, with one-step injection cost. |

The original task 376 “oracle” run retrieved nothing because keyword ranking missed the generated
primitive; it is not counted. The harness now supports explicit repeatable
`--oracle-primitive-id`, and task 376 was rerun with forced exact selection.

No held-out workflow incorporated the generated function. Nevertheless, supplied material changed
strategy and cost, including one large regression. This reinforces:

> Retrieval exposure itself is an intervention; provenance markers alone underestimate both
> positive guidance and negative anchoring.

Before expanding beyond this batch, automatic routing should reject or down-rank a parser when the
task has not established its required representation (`review_list_html`) or when the requested
answer can be obtained from a cheaper aggregate field.
