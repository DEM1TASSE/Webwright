# Rules: consolidate — organize the full candidate pool for one site

Site: `{{SITE}}`
Pool size: {{POOL_SIZE}} primitive(s)

## Inputs

- `in/context.json` — `{site, pool, workflows}`
- `in/code/<method>.py` — every pooled primitive's method body, extracted for direct reading.
- `in/sources/<workflow_id>.py` — the gold source scripts behind the pool.

This is the whole site pool at once, after all batches. Your job is deduplication, granularity,
and feature organization — not new capability.

## Output protocol

1. One file per operation under `out/ops/` (`000_*.json`, `001_*.json`, …).
2. Any new method body goes in `out/code/<name>.py`, referenced as `"method_code_file"`.
   `KEEP` never needs one — it must not alter code.

### Operations

```json
{"op": "KEEP", "source": "<id>", "feature": "snake_case"}

{"op": "MERGE", "sources": ["id1", "id2"], "feature": "snake_case",
 "replacement": {"primitive_id": "{{SITE}}/<feature>/<method>", "...": "..."},
 "reason": "..."}

{"op": "SPLIT", "source": "<id>", "feature_assignments": [],
 "replacements": [{"primitive_id": "{{SITE}}/<feature>/<method>", "...": "..."},
                  {"primitive_id": "{{SITE}}/<feature>/<method2>", "...": "..."}],
 "reason": "..."}
```

Every input primitive must be consumed **exactly once** — as a `KEEP` source, one `MERGE` source,
or one `SPLIT` source. Nothing may be silently deleted.

`KEEP` preserves code and contract untouched. `MERGE` and `SPLIT` replacements each carry complete
generated method code, boundary contracts, and source attribution with a concise explanation of
any generalization. A `SPLIT` produces two or more replacements.

### Features

Feature classes are composition components, not inheritance subclasses. Choose cohesive site
features.

**Name each feature with this site's own vocabulary** — the words it uses in its URLs, headings
and controls, as seen in `in/sources/*.py`. Do not reach for a generic category borrowed from
another site: a name with no grounding in these sources is rejected. If the sources say `issue`
nineteen times and never say `review`, the feature is `issues`.

Preserve the primitive/workflow boundary: site mechanics and typed parsing belong in primitives;
task filtering, aggregation, ranking, subjective decisions, and answer formatting stay in
workflows.

Do not emit package or class code. The deterministic class renderer builds `package.py` from your
operations after this stage.
