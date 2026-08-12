# Rules: consolidate — repair a pool that was built in pieces

Site: `{{SITE}}`

This site's primitives were built across several batches. Each batch saw only its own workflows,
so nobody has yet judged the pool as a whole. That is what this stage is for, and it is the only
stage with the authority to change what a primitive is.

Measured on a three-batch GitLab build, a pool assembled this way carries three defects a
single-batch build does not have. Look for each of them by name.

**Duplicates.** Two primitives acquire the same thing under different names because different
batches met it in different workflows — two dashboard project listings, two commit readers.

**Mixed operations.** A primitive that does two separable things, usually visible in its name:
`open_project_members_page_and_list_members` navigates *and* parses.

**Non-capabilities.** A primitive that only navigates and returns nothing typed —
`open_repository_landing_page`. Reaching a page is a step on a task's path, not a site
capability; the capability is whatever gets *read* there.

## Operations

Every pooled primitive must be consumed **exactly once**, as a `KEEP` source, one `MERGE` source,
or one `SPLIT` source. Nothing may be silently dropped.

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

`KEEP` preserves code and contract untouched. `MERGE` and `SPLIT` replacements each carry
complete method code, boundary contracts, and source attribution explaining the generalization.

## When to merge, and when not

`MERGE` is for primitives performing the **same** site operation: substitutable, same inputs,
same output records, differing only in how they were written. Two dashboard project listings that
return the same projects with different field names are one capability described twice — merge
them, keeping the richer field set.

**Belonging to the same feature is never a reason to merge.** A feature is a class and a class
holds many methods; three primitives that read reviews become three methods on the reviews class.
If a replacement wants a name like `*_tools` or `*_helpers`, you are grouping rather than merging
— use `KEEP` with a shared feature.

A pure navigation primitive has no reusable core to keep. Fold it into the primitive that reads
the page it opens: `MERGE` the two, and let the surviving method navigate and parse in one call.

## Features

Feature classes are composition components under the site class. Group by which part of the site
a primitive touches, and **name each feature with this site's own vocabulary** — the words it
uses in its URLs, headings and controls, as seen in `in/sources/*.py`. A name with no grounding
in these sources is rejected.

## Boundary

Site mechanics and typed parsing belong in primitives; task filtering, aggregation, ranking,
subjective decisions, and answer formatting stay in workflows. Merged and split replacements are
held to this exactly as a new primitive would be: typed records, no raw page text, no field that
merely echoes the URL the method just fetched.

Do not emit package or class code. The deterministic renderer builds `package.py` from your
operations.
