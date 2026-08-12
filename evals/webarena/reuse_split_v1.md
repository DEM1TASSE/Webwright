# Reuse-radius split (retrieve only, fixed train/test)

- **split**: fixed train/test over templates, per site
- **workflow_library**: one skill per TRAIN template with >= 3 distinct build instances
- **primitive_library**: site-level, from the build solves of all TRAIN templates
- **t1**: unseen instance of a TRAIN template -- arms: scratch | +workflow
- **t2**: unseen TEST template -- arms: scratch | +workflow | +primitive
- **t2_workflow_arm**: ablation expected to fail: a whole-task skill should not transfer across templates
- effective sample unit: **template**

## TRAIN (builds both libraries)

| site | templates | build runs | workflow skills | T1 templates | T1 tasks |
|---|---:|---:|---:|---:|---:|
| gitlab | 8 | 24 | 8 | 8 | 16 |
| map | 13 | 31 | 8 | 8 | 16 |
| reddit | 4 | 7 | 1 | 1 | 2 |
| shopping | 14 | 33 | 9 | 9 | 18 |
| shopping_admin | 11 | 31 | 10 | 10 | 20 |
| **total** | **50** | **126** | **36** | **36** | **72** |

## TEST (never touches a library)

| site | templates | T2 tasks | fresh |
|---|---:|---:|---:|
| gitlab | 7 | 11 | 1 |
| map | 10 | 19 | 5 |
| reddit | 0 | 0 | 0 |
| shopping | 10 | 15 | 6 |
| shopping_admin | 10 | 18 | 5 |
| **total** | **37** | **63** | **17** |

## Clusters and runs

- T1: **36 templates** / 72 tasks -- scratch vs +workflow
- T2: **37 templates** / 63 tasks -- scratch vs +workflow vs +primitive
- runs: 126 build + 72x2 + 63x3 = **459**
