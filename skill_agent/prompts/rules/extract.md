# Rules: extract — one workflow, no cross-workflow comparison

Site: `{{SITE}}`

Apply these rules to **one workflow at a time**. `in/context.json` lists the batch; each
workflow's source is `in/sources/<workflow_id>.py`, the exact `final_script.py` from a
gold-verified run of that task.

While extracting a given workflow, that is the only workflow you may reason from. Do not
deduplicate against the pool or against the other workflows in the batch, do not merge
candidates, and do not generate primitive code yet. You are enumerating what this one verified
run demonstrably knows how to do on this website.

## Your job

Read the source script properly before writing anything. Useful moves: `grep -n` for URLs,
selectors, `goto`, `locator`, `api`, `login`; print the functions with a short `ast` script;
follow what each parsed field is actually used for.

Then enumerate **every distinct reusable site operation the workflow actually demonstrates**.

## Output

Write `out/extractions/<workflow_id>.json` containing either:

```json
{"decision": "CANDIDATES",
 "candidates": [
   {"candidate_id": "<workflow_id>::<snake_name>",
    "proposed_method": "snake_case",
    "capability": "reusable website capability",
    "owns": ["..."],
    "does_not_own": ["..."],
    "input_contract": {"...": "..."},
    "output_contract": {"...": "..."},
    "source_evidence": {"workflow_id": "<workflow_id>", "template_id": "<template_id>",
      "code_quote": "representative source excerpt or concise source description",
      "explanation": "what was generalized from the workflow and why it supports this capability"}}]}
```

or, when nothing reusable is demonstrated:

```json
{"decision": "SKIP", "candidates": [],
 "skip_category": "BLOCKED|NON_WEBSITE|NO_REUSABLE_SITE_CAPABILITY",
 "reason": "specific reason"}
```

## Boundary rules

- One workflow is sufficient evidence. Enumerate every distinct reusable site operation it shows.
- UI/DOM/page-text acquisition **is** valid when the candidate itself parses it into typed
  records. Handing raw page text or DOM back to a workflow is not.
- Primitives own: site selectors, URL patterns, endpoint shapes, authentication, pagination, and
  stable displayed semantics.
- Workflows keep: task filtering, aggregation, ranking, subjective classification, answer
  formatting. Local git/filesystem operations are not website primitives.
- A failed or blocked attempted mutation does not prove that mutation capability.

## Do not overfit the record to this task

At the same demonstrated acquisition boundary, preserve the stable objective identity, temporal,
state, value, link, and pagination/completeness fields the evidence actually exposes. This is not
license to invent undocumented fields.

Specifically, do not collapse contributor identity to a display name, issue records to
title/href, commit timestamps to one ambiguous date field, or paginated search results to an
apparently complete list when richer facts or completeness signals are demonstrated.

Reserve the input name `page` for the component's browser object (`self.page`). Numeric
pagination inputs are called `page_number` in input contracts.

Source evidence is attribution, not a demand to copy code verbatim: explicitly describe how
hard-coded instance values become parameters and how task-specific logic is removed. Do not
discard a real capability merely because an API or embedded-JSON source would be more stable.
