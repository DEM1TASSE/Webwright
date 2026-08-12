# Consolidate one site's skill library

Site: `{{SITE}}` — {{POOL_SIZE}} primitive(s) in the pool

Every batch for this site has been built and committed. The pool grew one batch at a time, so
nobody has yet looked at it as a whole. That is your job.

## What to decide

- **Duplication** — two batches may have produced near-identical capabilities under different
  names.
- **Granularity** — one primitive may be doing two separable jobs; another may be a fragment
  that only makes sense merged.
- **Organization** — every primitive belongs to a cohesive site *feature* (`auth`, `commits`,
  `reviews`, `orders`, `routing`, …), rendered as a component class under the site class.

You are **not** adding capability. Nothing may be silently dropped: every input primitive must
be consumed exactly once, as a `KEEP` source, one `MERGE` source, or one `SPLIT` source.

## Inputs

- `in/context.json` — `{site, mode, workflows}`
- `in/code/<method>.py` — every pooled primitive's method body, as real Python
- `in/sources/<workflow_id>.py` — the gold scripts the pool was built from
- `in/rules/consolidate.md` — the operation shapes and boundary rules. **Read it first.**
- `in/previous_attempt_feedback.json` — present only if an earlier attempt was rejected.

## What you owe

One file per operation under `out/ops/`, and any new method body under `out/code/` referenced as
`"method_code_file"`. `KEEP` must not alter code, so it never needs one; only `MERGE` and
`SPLIT` produce new bodies, each with complete code, contracts, and source attribution.

Read the pooled code before deciding anything. Two primitives with similar names may parse
different pages; two with different names may do the same thing.

## Verifying

```bash
python -m skill_agent.verify
```

Reports the pool, composes your operation files, and validates the consolidation — including
that every pooled primitive is consumed exactly once. Run it as often as you like.

Exit 0 means you are done. Set `"done": true` and summarize the final feature layout in
`final_response`.
