# Reuse-radius split (retrieve only)

- workflow library: per template, from that template's build solves; fixed split; measures T1
- primitive library: per site, from build solves of every template except the held-out one; leave-one-template-out; measures T2
- the scratch arm is shared, so T1 and T2 are paired against the same baseline runs
- effective sample unit: **template**

## Solve corpus (what to run to build the libraries)

| site | templates | build runs | held-out tasks | fresh templates |
|---|---:|---:|---:|---:|
| gitlab | 15 | 33 | 22 | 1 |
| map | 23 | 50 | 39 | 9 |
| reddit | 4 | 7 | 4 | 4 |
| shopping | 24 | 49 | 31 | 10 |
| shopping_admin | 21 | 49 | 35 | 7 |
| **total** | **87** | **188** | **131** | **31** |

## T1 — same-template reuse (fixed split, workflow library)

| site | templates | held-out tasks |
|---|---:|---:|
| gitlab | 4 | 8 |
| map | 4 | 8 |
| reddit | 1 | 2 |
| shopping | 4 | 8 |
| shopping_admin | 4 | 8 |
| **total** | **17** | **34** |

Arms: `scratch` vs `+workflow`. Clusters: **17 templates**.

## T2 — cross-template reuse (leave-one-template-out, primitive library)

| site | folds | held-out tasks | library built from |
|---|---:|---:|---|
| gitlab | 12 | 22 | 14 other templates |
| map | 20 | 39 | 22 other templates |
| reddit | 2 | 4 | 3 other templates |
| shopping | 17 | 31 | 23 other templates |
| shopping_admin | 18 | 35 | 20 other templates |
| **total** | **69** | **131** | |

Arms: `scratch` vs `+primitive`. Clusters: **69 templates**. Each fold needs its own offline library build (69 distillations, no browser).

## Run budget

- collect solves: **188** agent runs (gold-gated; failures may be retried on the same instance, since build material is not held out)
- scratch arm: **131** runs (shared by T1 and T2)
- workflow arm: **34** runs
- primitive arm: **131** runs
- **total agent runs: 484**, plus 69 offline library builds
