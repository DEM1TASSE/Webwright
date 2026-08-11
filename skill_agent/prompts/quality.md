# Stage: quality — independent quality-and-coverage gate

Site: `{{SITE}}`

You did not write these operations. Judge them; do not repair them.

## Inputs

- `in/context.json` — `{site, operations, candidate_attribution, extractions}`
- `in/sources/<workflow_id>.py` — the gold source scripts the evidence cites.
- `in/code/<method>.py` — the proposed method bodies, extracted for direct reading.

Read the cited evidence before ruling on a claim. If an operation says it generalized a selector
or endpoint from a workflow, go look at that workflow.

## Output

Write `out/verdicts.json`:

```json
{"verdicts": [{"operation_index": 0, "verdict": "PASS|FAIL", "reason": "..."}],
 "rejection_verdicts": [{"candidate_id": "...", "verdict": "PASS|FAIL", "reason": "..."}]}
```

Cover **every** `ADD`/`UPDATE` operation in `verdicts`, and **every** `candidate_attribution`
entry whose decision is `REJECT` in `rejection_verdicts`, each exactly once.

## What PASS requires

- Source evidence directly supports the site operation.
- Output is typed.
- The method owns site-specific acquisition and parsing, but not task-specific filtering,
  aggregation, ranking, subjective decisions, or answer formatting.
- `owns` and `does_not_own` are consistent, and code and contract agree.

Parsing UI/DOM/page text internally into typed site records is valid and must not be failed
merely because an API is unavailable. Parameterized site-native search/date/page controls are
valid; an arbitrary filter copied from the task question is not.

FAIL unsupported, invented, contradictory, overly task-specific, raw-output, or cosmetic
abstractions.

Website-specific authentication mechanics **are** valid primitives when the evidence demonstrates
the site's login URL and form selectors, submit behavior, and authenticated-state detection. Do
not reject such a candidate as generic browser setup merely because credentials are parameters.

## Lossy-projection and completeness failures

FAIL a lossy, task-tailored projection when the cited evidence demonstrates additional stable
objective record fields needed to interpret identity, time, state, links, or collection
completeness.

FAIL an output that looks like a complete collection but neither traverses nor reports
pagination/completeness.

Do not demand fields that are absent from the supplied evidence.

## Judging a REJECT

A `REJECT` passes only when removing task logic leaves no reusable website acquisition or parsing
core at all. In particular:

- a count candidate that demonstrates listing record IDs must be narrowed to a list-records
  primitive, not rejected;
- a candidate that mixes authentication, report extraction, and format shaping must retain the
  demonstrated site report-row acquisition as a narrower primitive;
- a raw-text output defect should be narrowed to typed facts when the evidence supports them.

Mark such `REJECT` decisions `FAIL`, so the build stage regenerates an `ADD`/`UPDATE` instead.

## Finish

Run `python -m skill_agent.check quality` until it exits 0, then set `"done": true`.
A `FAIL` verdict is a legitimate outcome — the checker validates that your verdicts are complete
and well-formed, not that everything passed.
