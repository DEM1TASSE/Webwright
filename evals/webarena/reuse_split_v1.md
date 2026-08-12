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
| gitlab | 7 | 21 | 7 | 7 | 14 |
| map | 13 | 31 | 8 | 8 | 16 |
| reddit | 2 | 5 | 1 | 1 | 2 |
| shopping | 13 | 32 | 9 | 9 | 18 |
| shopping_admin | 11 | 31 | 10 | 10 | 20 |
| **total** | **46** | **120** | **35** | **35** | **70** |

## TEST (never touches a library)

| site | templates | T2 tasks | fresh |
|---|---:|---:|---:|
| gitlab | 5 | 9 | 0 |
| map | 10 | 19 | 5 |
| reddit | 0 | 0 | 0 |
| shopping | 10 | 15 | 6 |
| shopping_admin | 8 | 16 | 3 |
| **total** | **33** | **59** | **14** |

## Clusters and runs

- T1: **35 templates** / 70 tasks -- scratch vs +workflow
- T2: **33 templates** / 59 tasks -- scratch vs +workflow vs +primitive
- runs: 120 build + 70x2 + 59x3 = **437**
