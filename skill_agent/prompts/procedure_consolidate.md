# Consolidate one site's primitives, built across several batches

Site: `{{SITE}}` — {{POOL_SIZE}} primitive(s) in the pool, from {{BATCH_COUNT}} batches

Each batch saw only its own workflows and the pool as it stood. None of them saw the site whole.
You are the first, and you are the only stage that can change what a primitive is.

## What to look for

- **Duplicates** — different batches met the same capability in different workflows and each
  named it their own way.
- **Mixed operations** — one primitive doing two separable things, often visible in a name
  containing `and`.
- **Non-capabilities** — a primitive that only navigates and returns nothing typed. Reaching a
  page is a step on a task's path; the capability is what gets read there.
- **Organization** — every surviving primitive belongs to a feature class, named in this site's
  own vocabulary.

You are not adding capability. Every pooled primitive is consumed exactly once — kept, merged
into something, or split apart. Nothing disappears silently.

## Inputs

- `in/context.json` — `{site, mode, workflows}`
- `in/code/<method>.py` — every pooled primitive's method body, as real Python
- `in/sources/<workflow_id>.py` — the gold scripts the pool was built from
- `in/rules/consolidate.md` — the operation shapes and the merge discipline. **Read it first.**
- `in/previous_attempt_feedback.json` — present only if an earlier attempt was rejected.

## What you owe

One file per operation under `out/ops/`, and any new method body under `out/code/` referenced as
`"method_code_file"`. `KEEP` never needs one — it must not alter code.

Read the pooled code before deciding anything. Two primitives with similar names may parse
different pages; two with different names may do the same thing.

## Verifying

```bash
python -m skill_agent.verify
```

Composes your operation files and checks that every pooled primitive is consumed exactly once,
that replacements hold up as primitives in their own right, and that feature names are grounded
in this site.

Exit 0 means you are done. Set `"done": true` and summarize what you merged, split and kept in
`final_response`.
