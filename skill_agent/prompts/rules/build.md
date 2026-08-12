# Rules: build — reconcile extracted capabilities into an unclassified primitive pool

Site: `{{SITE}}`
Batch: {{BATCH_SIZE}} workflow(s) — {{WORKFLOW_IDS}}

## Inputs

- `in/context.json` — `{site, batch, extractions, pool, catalog_index, retrieved_primitives, all_workflows}`
- `in/sources/<workflow_id>.py` — the gold `final_script.py` behind every workflow in the batch.
- `in/extractions/<workflow_id>.json` — the accepted stage-1 candidates, split out for easy reading.

`pool` is the current candidate state (empty on the first batch). You are producing operations
against it. Do not classify features and do not generate a package class — that happens later.

## Your job

Turn the extracted candidates into concrete, runnable primitive methods with real code, and say
what each source workflow and each candidate contributed.

Read the actual source scripts for the selectors, endpoints, and parsing you are generalizing.
The extraction records tell you *what* was demonstrated; the source tells you *how*.

## Output protocol

Do not try to write one giant JSON. Write small files and assemble them:

1. One file per operation: `out/ops/000_<short_name>.json`, `out/ops/001_<short_name>.json`, …
   Sorted filename order is the operation index used by attribution.
2. Method bodies go in real Python files under `out/code/`, referenced from the operation as
   `"method_code_file": "code/<name>.py"` instead of `"method_code"`. Write normal Python — no
   JSON escaping.
3. `out/workflow_attribution.json` and `out/candidate_attribution.json` — JSON arrays.

### Operation shapes

`ADD` and `UPDATE` carry a complete `replacement`:

```json
{"op": "ADD",
 "replacement": {
   "primitive_id": "{{SITE}}/<method>",
   "method": "snake_case",
   "method_code_file": "code/<method>.py",
   "capability": "...",
   "owns": ["..."], "does_not_own": ["..."],
   "input_contract": {"...": "..."}, "output_contract": {"...": "..."},
   "requires": ["..."], "provides": ["..."], "supported_patterns": ["..."],
   "source_evidence": [{"workflow_id": "...", "template_id": "...",
     "code_quote": "representative source excerpt or concise source description",
     "explanation": "what was generalized from the source"}]}}
```

`UPDATE` additionally has `"target_id"`, and is valid only when capability identity and the core
input/output contract stay stable. It returns the **entire** replacement, never a patch.
`SKIP` has `"reason"`.

### Method code rules

Methods belong to a feature component class whose `__init__` stores `self.page`. So:

- every method starts with `self` and uses `self.page` for browser access;
- **never** expose a separate browser `page` parameter — the name `page` is reserved for the
  browser object. API/UI pagination inputs are named `page_number`, and are represented that way
  in `input_contract`;
- the one public method's Python name must equal the `method` field — if `method` is
  `list_commits`, write `def list_commits(self, ...)`, never `def method(...)`;
- private helpers start with `_`;
- public primitives do not call other public primitives. Use `requires`/`provides` for
  environment-state preconditions such as being authenticated;
- the rendered class is `__init__(self, page): self.page = page` and nothing more, so
  `self.<anything else>` does not exist. Inventing `self.base_url` parses fine and raises
  AttributeError on the first real call.

Where the site's base URL comes from, since the class cannot hold it:

- a method that **navigates** may derive it from where the browser already is:
  `urlparse(self.page.url)` gives scheme and netloc;
- a method that only calls an **API** must take it as an explicit parameter — it never
  navigates, so `self.page.url` may still be `about:blank`. Declare it in `input_contract`.

**Everything in this section constrains how you write a primitive. None of it is a reason to
reject a capability.** If a source workflow does something in a way these rules forbid, you
reimplement it — the capability is demonstrated either way. Rejecting a real site capability
because its evidence used a forbidden technique throws away the thing you were sent to find.

Import only the standard library. A method that imports a third-party package this project does
not depend on raises ModuleNotFoundError on its first call, and nothing about the code looks
wrong. Use `urllib` for HTTP — including authenticated requests, by forwarding
`self.page.context.cookies()` as a `Cookie` header — and `self.page` for anything the browser
should do. A source that used `requests` is still evidence of the capability: write the same
acquisition with `urllib`.

Never hard-code the deployment's host or IP into a method — take the base URL as a parameter
instead. The address is environment state that changes between deployments, so a primitive that
bakes it in stops working the moment the library moves.

This is emphatically **not** a reason to reject an endpoint that lives somewhere other than the
web app. Many sites put a service on its own host or port — a geocoding service, a routing
engine, a search backend — and reaching it is exactly the kind of site capability worth
capturing. Give the method that service's base URL as a parameter, declare it in
`input_contract`, and keep the capability.

Keep the code portable across Python versions: never reuse the same quote character inside an
f-string expression (`f'{d['key']}'` is a syntax error before 3.12 — use `f"{d['key']}"` or a
local variable). The validator parses with whichever interpreter runs the build, so it will not
catch this for you.

Check your code parses before verifying: `python -c "import ast; ast.parse(open('out/code/x.py').read())"`.

### Primitive boundary

Own site selectors, endpoints, authentication, pagination, and stable site-output semantics.
Return typed objective facts.

Never return a `Locator`, `ElementHandle`, raw DOM/HTML, arbitrary page text, or an untyped blob.
Workflows own requested filtering, subjective judgement, aggregation, ranking and comparison,
question-specific stopping, and final formatting. No generic regex/HTTP/browser-setup primitives.

Do not create `count_*` primitives that compute `len()` over records you just acquired — return
the typed records and let the workflow count. A total the website itself supplies may be returned
as an objective field alongside the records.

Formatting seconds into an answer string is workflow logic; parsing a site's *displayed* duration
into typed seconds is a valid primitive.

Typed record schemas are lossless with respect to the stable objective fields demonstrated at the
acquisition boundary — not minimal projections tailored to the source task. Preserve distinct
identity fields, distinct site timestamps, stable hrefs/ids/state, and explicit pagination or
enumeration-completeness metadata when evidence supports them. Never claim a collection is
complete merely because the source task stopped after one page.

### Attribution

Every workflow in the batch appears exactly once in `workflow_attribution`:

```json
{"workflow_id": "...", "decision": "CONTRIBUTED", "operation_indices": [0]}
{"workflow_id": "...", "decision": "SKIP", "reason": "..."}
```

Every supplied extracted candidate appears exactly once in `candidate_attribution`:

```json
{"candidate_id": "...", "decision": "ADD|UPDATE", "operation_index": 0}
{"candidate_id": "...", "decision": "COVERED", "target_id": "<site>/<existing_method>", "reason": "..."}
{"candidate_id": "...", "decision": "REJECT", "target_id": null, "reason": "..."}
```

`COVERED` means a primitive that **already exists** — in the pool, or in an operation you are
adding in this batch — acquires the same thing. Name it in `target_id`; a `COVERED` without a
real primitive to point at is not covered, it is dropped. "Omitted to keep the batch small" is
never a reason: every candidate either becomes an operation, is genuinely covered by a named
primitive, or is rejected for a defect you can state.

`REJECT` is allowed only for a boundary or evidence defect — never because UI parsing is less
attractive than an API, and never because the batch would otherwise be larger. Every `ADD`/`UPDATE` operation must be linked from at least one extracted
candidate. Workflow attribution summarizes these candidate-level decisions.

Every `ADD`/`UPDATE` cites supplied gold workflows and explains how concrete code was generalized.
Hard-coded project/product/date/branch values become inputs where that preserves the site
operation. Source excerpts may be shortened or paraphrased. Do not invent source workflows,
unsupported site behavior, or source answers.
