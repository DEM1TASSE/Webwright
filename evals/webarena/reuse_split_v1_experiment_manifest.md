# reuse_split_v1 experiment manifest

## Frozen inputs

- Split: `reuse_split_v1.json`
- Split SHA-256: `01e77eb3b16ce9e75a5aab57a1e25ae80e16e54f7ce23c6cef3ce30b2f58f4f1`
- Model config: `model_gateway_54.yaml`
- Model-config SHA-256: `085881eaea759618d1096406e5c633b88d799af0c47608e304c70235080b2e86`
- Evaluator commit: `6473f72db5dcefc97b5725b59e734504edc28a21`
- Timeout: 900 seconds per agent run

## Frozen arms

- Scratch: current runtime/evaluator, no library material.
- Workflow: standalone same-template parameterized workflow from the pre-cross-template factory at
  commit `590beeab9b539cf938466e56128c4e5695a469ef`,
  `src/webwright/skill_factory/update.py` (blob SHA-256
  `c19e8ef338c9cec6ed5bf83f57204ce052ecef9a794c1f691785d1b38fac7c0b`). Internal helpers are
  allowed; it must not import or consume the site primitive package.
- Primitive: audited v4 pipeline at commit `14b8adb`,
  `src/webwright/skill_factory/audited_primitive_build.py` (blob SHA-256
  `4b7d279825f848a42cc47d648e7ba08877ef634f12fcf9c266e9a618684afb0e`). Route from metadata with
  `use/adapt/skip`; inject full selected code directly before agent planning; vendor into the final
  standalone script. Do not use scratch-first and do not retrieve workflows in this arm.

## Isolation

- TRAIN build tasks feed libraries only.
- T1 tasks are unseen instances of TRAIN templates.
- T2 templates never feed either library.
- Scratch, workflow, and primitive use separate run/result roots.
- Historical results are development evidence only and are not mixed into formal results.

## Pre-evaluation retrieve-only correction

The legacy sampler filtered only on evaluator class. A semantic audit before formal evaluation
excluded TRAIN task 792 and T2 tasks 805, 807, 783, 789, 723, 726, 491, and 790. Their intents are
state-changing and/or their expected result encodes an unavailable action rather than retrieval.
The task 792 attempt remains in the raw TRAIN log but was incorrect and never entered either
library. The formal eligible counts are TRAIN 120, T1 70, and T2 59.
