# Build one batch of a site skill library

Site: `{{SITE}}` — batch {{BATCH}}, {{BATCH_SIZE}} workflow(s): {{WORKFLOW_IDS}}

## What you are doing

Gold-verified web workflows are complete, standalone solutions to individual tasks. Buried in
them is knowledge about the *website* — how to authenticate, which endpoint or selector yields
which record, how pagination works — that any task on that site could reuse. Your job is to lift
that out as **primitives**: site-scoped, reusable, typed acquisition methods.

What stays behind in the workflow: filtering the question asked for, aggregating, ranking,
subjective judgement, and formatting the answer. A primitive that quietly absorbs any of those
is the failure this whole exercise exists to prevent.

## Inputs

- `in/context.json` — `{site, batch, pool, catalog_index, retrieved_primitives, all_workflows}`
- `in/sources/<workflow_id>.py` — the exact `final_script.py` from each gold-verified run
- `in/rules/extract.md`, `in/rules/build.md` — the boundary rules. **Read the relevant one
  before doing that part.** They are the specification; this document is only the shape.
- `in/previous_attempt_feedback.json` — present only if an earlier attempt was rejected.
  Read it first if it exists.

`pool` is what the library already holds from earlier batches — empty on the first one.

## What you owe

**1. One extraction per workflow.** `out/extractions/<workflow_id>.json`

Read `in/rules/extract.md`, then read each source properly — grep for URLs, selectors, `goto`,
`locator`, API calls; run a short `python - <<'PY'` over it if that helps. Enumerate what that
one run demonstrably knows how to do on this website.

Do one workflow at a time. While extracting a given workflow, do not deduplicate against the
others or against the pool, and do not write code yet. Enumerating first and merging later is
deliberate: comparing too early makes you drop capabilities before you have seen them all.

**2. A build proposal.** Read `in/rules/build.md` for the operation shapes, method-code rules,
and attribution requirements.

- one file per operation under `out/ops/` — sorted filename order is the operation index
- method bodies as real Python under `out/code/`, referenced as `"method_code_file"`
- `out/workflow_attribution.json` and `out/candidate_attribution.json`

## Verifying

```bash
python -m skill_agent.verify
```

One command, run it as often as you like. It reports what is still missing, composes your
operation files into a proposal, validates everything, and puts your work in front of two
**independent readers** — each a separate agent with an empty context:

- once every workflow is extracted, a reader checks the extractions against the sources for a
  demonstrated capability nobody claimed. This is the one place where losing a capability is
  invisible to everything downstream, so it is checked before you build;
- once the proposal is structurally clean, a judge reads your code and the evidence it cites and
  rules PASS or FAIL per operation.

A FAIL, or a capability reported as missed, is information rather than an accident. Read the
reason and fix the thing — usually by extracting the capability that was passed over, by
narrowing what a primitive owns, or by restoring record fields the evidence supports. Do not
re-submit unchanged work hoping for a different ruling: unchanged work reuses the existing one.

Exit 0 means you are done. Set `"done": true` and summarize what you added in `final_response`.

If you genuinely cannot get an operation past the judge, drop that operation and deliver a
smaller, honest batch rather than weakening a primitive's contract until the objection goes
away. Say so in `final_response`.
