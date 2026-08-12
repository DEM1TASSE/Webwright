# Rules: classify — assign every pooled primitive to a site feature

Site: `{{SITE}}`

The pool holds primitives that already passed the boundary judge. Their capabilities, contracts
and code are settled. **Your only decision is which feature class each one belongs to.**

## Output

One operation per pooled primitive:

```json
{"op": "KEEP", "source": "<site>/<method>", "feature": "snake_case"}
```

Every pooled primitive must appear exactly once. `KEEP` preserves code and contract untouched —
you are labelling, not rewriting. Nothing may be dropped and nothing may be combined.

## Choosing features

A feature is a component class under the site class: `GitLabSite.commits`, `ShoppingSite.orders`.
Group primitives by which part of the site they touch, so a consumer looking for "the thing that
reads orders" finds it where it expects to.

**Name each feature with this site's own vocabulary** — the words it uses in its URLs, headings
and controls, as seen in `in/sources/*.py`. Do not reach for a generic category borrowed from
another site: if the sources say `issue` nineteen times and never say `review`, the feature is
`issues`.

Several primitives sharing a feature is normal and expected: a feature is a class, and a class
holds many methods. Three primitives that read reviews become three methods on the reviews
class. They are never combined into one — merging distinct operations would be the one
irreversible mistake available at this stage, and it is not an operation you have.

A feature with one primitive is fine. Do not invent groupings to balance the classes, and do not
split a coherent area into `orders_list` and `orders_detail`.

## Boundary

Classification does not change the primitive/workflow boundary: site mechanics and typed parsing
belong in primitives; task filtering, aggregation, ranking, subjective decisions, and answer
formatting stay in workflows. If a pooled primitive looks wrong, classify it anyway — it already
passed the judge, and this stage has no authority to rewrite it.

Do not emit package or class code. The deterministic renderer builds `package.py` from your
feature assignments.
