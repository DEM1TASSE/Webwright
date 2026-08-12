# Judge: did the extraction miss a capability this site demonstrably has?

Site: `{{SITE}}`

You did not write these extractions. Your only question is **completeness**: reading each source
workflow yourself, is there a reusable site capability it demonstrates that no candidate claims?

This is where capability is lost. Everything downstream — building, consolidating, the boundary
gate — only ever sees what extraction enumerated. A capability missed here is invisible for the
rest of the pipeline, so nothing else can catch it.

## Inputs

- `in/context.json` — `{site, mode, extractions}`, one extraction per workflow
- `in/sources/<workflow_id>.py` — the exact gold `final_script.py` behind each workflow

Read the sources. Do not rule from the extraction summaries alone — the whole point is to see
what a reader of the summary cannot.

A concrete failure to look for: a workflow visits more than one distinct site area on its way to
its answer, and only the last one became a candidate. Getting to a project's members page may
mean first finding the project; checking whether a repository is reachable is a capability even
when the task went on to do something else. Secondary navigation is still demonstrated
capability.

## What counts as a miss

A miss is a **site acquisition or parsing operation** the source performs that no candidate
covers, and that would be reusable by another task on this site:

- a distinct page or endpoint visited and parsed for facts;
- a distinct authenticated action performed to reach those facts;
- a distinct record shape read from the page.

These are **not** misses:

- task-level filtering, aggregation, ranking, comparison or answer formatting — those belong to
  the workflow, not to a primitive;
- local git or filesystem work, which is not a website capability;
- an attempted mutation that the site blocked or that failed — a failed attempt demonstrates
  nothing;
- a navigation that only passes through a page without reading anything from it.

Do not invent a capability to have something to report. An extraction that genuinely captured
everything reusable should be marked complete.

## Output

Write `out/extraction_review.json`:

```json
{"reviews": [
  {"workflow_id": "task123_t45",
   "verdict": "COMPLETE|INCOMPLETE",
   "missed": [{"capability": "what the source demonstrates that no candidate claims",
               "evidence": "the part of the source that shows it",
               "why_reusable": "how another task on this site would use it"}],
   "reason": "one line; for COMPLETE, what you checked"}]}
```

Cover every workflow in `in/context.json` exactly once. `missed` is empty for `COMPLETE`.

## Finish

Run `python -m skill_agent.verify` until it exits 0, then set `"done": true`.
`INCOMPLETE` is a legitimate ruling — the checker validates that your review is complete and
well-formed, not that everything passed.
