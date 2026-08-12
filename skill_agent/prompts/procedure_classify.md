# Classify one site's primitives into feature classes

Site: `{{SITE}}` — {{POOL_SIZE}} primitive(s) in the pool

Every batch for this site has been built and committed, and every primitive in the pool has
already passed the boundary judge. Nothing here is under review any more.

**Your job is one decision per primitive: which feature class does it belong to?** The renderer
turns those labels into component classes under the site class — `GitLabSite.commits`,
`ShoppingSite.orders` — so a consumer finds a capability where it expects to.

You are not adding, removing, combining or rewriting anything. Every pooled primitive is
labelled exactly once, with its code and contract untouched.

## Inputs

- `in/context.json` — `{site, mode, workflows}`
- `in/code/<method>.py` — every pooled primitive's method body, as real Python
- `in/sources/<workflow_id>.py` — the gold scripts the pool was built from
- `in/rules/consolidate.md` — the operation shape and how to choose feature names. **Read it
  first.**
- `in/previous_attempt_feedback.json` — present only if an earlier attempt was rejected.

## What you owe

One file per primitive under `out/ops/`:

```json
{"op": "KEEP", "source": "<site>/<method>", "feature": "snake_case"}
```

Read the pooled code before labelling. Two primitives with similar names may read different
pages; two with different names may belong to the same part of the site.

## Verifying

```bash
python -m skill_agent.verify
```

Reports the pool, composes your operation files, and checks that every pooled primitive is
labelled exactly once. Run it as often as you like.

Exit 0 means you are done. Set `"done": true` and summarize the feature layout in
`final_response`.
