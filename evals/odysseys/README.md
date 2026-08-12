# Odysseys site-level primitive adapter

Odysseys tasks can span several live websites. This adapter keeps the existing audited primitive
library site-scoped and introduces a reviewed segment manifest between the benchmark task and the
retriever. Each site segment receives its own scratch plan and gate decision; answer-only segments
never receive primitive code.

## Files

- `site_primitives.py`: validates reviewed segments and independently routes each site.
- `adapt_source_run.py`: discovers per-site URL/action/screenshot/code evidence from a judged run
  and emits a conservative human-review queue.
- `export_builder_manifest.py`: converts only approved, rubric-passing adapter records into the
  existing audited builder contract.
- `build_site_library.py`: admits only scratch segments whose assigned official rubrics scored 1.
- `cross_task_eval.py`: runs scratch or a single task with all site-level routing decisions frozen
  before browser execution.
- `segments.example.json`: reviewed segmentation for the first smoke task.

## Build flow

First run source tasks from scratch and score them with the official Odysseys per-rubric judge.
For each task, review a segment manifest with an exact site, site-level template ID, goal, required
fields, and rubric IDs. Also extract a reviewed site-only code file for every site segment and list
it under `segment_code`; the builder deliberately refuses to expose a full multi-site script to a
site builder. Then create a source manifest like `source_manifest.example.json` and run:

```bash
PYTHONPATH=src python evals/odysseys/adapt_source_run.py TASK_ID \
  --tasks odysseys.json --workspace RUN_WORKSPACE \
  --judge-results eval_results.json --output adapter_reviews

# Review adapter_review.json, supply exact rubric/template/goal approvals, rerun with --approvals,
# then combine the approved records:
PYTHONPATH=src python evals/odysseys/export_builder_manifest.py \
  adapter_reviews/*/adapter_review.json --output builder_inputs
```

The initial adapter output always says `needs_review`; automatic URL/rubric matching is a proposal,
not admission. A segment becomes admitted only when review status is approved, every mapped rubric
scored 1, it has a frozen template ID, and site-specific code evidence was found.

Build the resulting manifest:

```bash
PYTHONPATH=src python evals/odysseys/build_site_library.py \
  --source-manifest source_manifest.json \
  --judge-results eval_results_full_traj_per_rubric.json \
  --output odysseys_site_library \
  --model-config model.yaml
```

A site segment is excluded if any rubric assigned to it failed. Primitive-arm runs are rejected as
source evidence. The resulting directory uses the same
`<site>/final_candidate/index.json` layout as the WebArena audited library.

## Held-out execution

Scratch:

```bash
PYTHONPATH=src python evals/odysseys/cross_task_eval.py TASK_ID scratch \
  --tasks odysseys.json --runs runs -c model.yaml
```

Treatment:

```bash
PYTHONPATH=src python evals/odysseys/cross_task_eval.py TASK_ID primitive \
  --tasks odysseys.json --segments heldout_segments.json \
  --library odysseys_site_library --runs runs \
  --model-config model.yaml -c model.yaml
```

The treatment writes one retrieval record per segment plus a task-level `site_routing.json`.
Missing site libraries and answer-only segments deterministically skip; they never fall back to a
primitive from another site.

## Experimental boundary

Freeze source/held-out task IDs and template IDs before building. Held-out task trajectories,
answers, and judge outputs must not enter the source manifest. Report official rubric average and
perfect-task rate, plus per-segment route/apply/skip and primitive-use counts.
