# Mentor sync: cross-template primitives on WebArena

Status: **temporary snapshot, 2026-08-07 22:xx UTC**. The 32-train / 24-test experiment is
still finishing its last Shopping Admin pairs. Do not treat the numbers below as final.

## One-minute summary

We are testing whether a skill library can reuse smaller site-specific capabilities across
different task templates on the same website. The MVP treats a primitive as **synthesis
material**, not a runtime dependency: retrieved code is offered to the agent, while every saved
workflow remains standalone. This avoids version pinning, dependency DAGs, and replay cascades.

The current experiment uses four independent site libraries (Shopping, GitLab, Shopping Admin,
and Map). A seeded template-level split selects one instance from each template, with no template
overlap between train and test:

- 32 train tasks: 8 distinct templates per site;
- 24 test tasks: 6 unseen templates per site;
- paired test arms: scratch and workflow-first routed;
- retrieve-only tasks; no manual selection by difficulty, scratch outcome, or primitive overlap;
- seed: `20260807`.

At the current 22/24-pair snapshot, success is tied at **10/22 (45.5%)** in both arms, with
**3 Wins / 3 Losses / 7 both-correct / 9 both-wrong**. Routed uses **13.14 agent steps** on
average versus **17.36** for scratch (-24.3%). This step comparison excludes the router's own LLM
call and injected-token cost.

## Implemented pipeline

The pushed implementation is commit `421eb94` on branch `cross-task-primitives`.

1. **Seeded split** — template-level SHA-256 ordering is deterministic and input-order
   independent. Train/test templates are strictly disjoint.
2. **Gold admission** — only train workflows with evaluator score 1 enter library construction.
3. **Per-site libraries** — each website has an independent workflow and primitive catalog;
   cross-site retrieval is impossible by construction.
4. **Primitive updater** — proposes `ADD / MODIFY / SPLIT / ARCHIVE / NO_CHANGE`, checks Python
   syntax, standalone/self-contained code, provenance, signatures, and source-answer leakage.
   No primitive used in this experiment was hand-written.
5. **Workflow-first router** — exact/runnable workflow when available; otherwise related workflow
   adaptation; otherwise primitive metadata retrieval; otherwise scratch. Primitive metadata is
   ranked first and full code is fetched only for `use/adapt`.
6. **Vendoring/copy-on-use** — historical workflows contain complete standalone code and do not
   import catalog primitives. Catalog updates therefore do not break old workflows.
7. **Bounded execution** — resumable per-site lanes, process-group timeout cleanup, explicit
   evaluator provenance, frozen-library hash verification, and paired aggregation.

Main implementation paths:

- `evals/webarena/sample_cross_task_split.py`
- `evals/webarena/run_cross_task_plan.py`
- `evals/webarena/cross_task_eval.py`
- `evals/webarena/build_generated_primitives.py`
- `evals/webarena/aggregate_cross_task_results.py`
- `src/webwright/skill_factory/primitive_catalog.py`
- `src/webwright/skill_factory/primitive_update.py`
- `src/webwright/skill_factory/primitive_retrieve.py`
- `src/webwright/skill_factory/route.py`

## Library construction

All 32 randomly selected train tasks completed without infrastructure failures. Gold admission:

| site | selected | gold-admitted | workflows | primitives |
|---|---:|---:|---:|---:|
| Shopping | 8 | 4 | 4 | 2 |
| GitLab | 8 | 7 | 7 | 1 |
| Shopping Admin | 8 | 3 | 3 | 2 |
| Map | 8 | 3 | 2 | 2 |
| **Total** | **32** | **17** | **16** | **7** |

The one-workflow difference for Map comes from workflow grouping/distillation; all three admitted
records remain in provenance. The four libraries were frozen before reset and test.

## Temporary test result (22/24 complete pairs)

| site | pairs | scratch | routed | Wins | Losses | scratch steps | routed steps |
|---|---:|---:|---:|---:|---:|---:|---:|
| Shopping | 6/6 | 3 | 4 | 1 | 0 | 15.00 | 12.33 |
| GitLab | 6/6 | 3 | 2 | 1 | 2 | 13.83 | 12.50 |
| Shopping Admin | 4/6 | 2 | 3 | 1 | 0 | 25.00 | 17.50 |
| Map | 6/6 | 2 | 1 | 0 | 1 | 18.17 | 11.67 |
| **Current total** | **22/24** | **10** | **10** | **3** | **3** | **17.36** | **13.14** |

Routing decisions among completed pairs: 15 `adapt`, 7 `skip`.

Interpretation so far:

- The larger random split is not ceiling-dominated: 9/22 pairs are both-wrong, unlike the earlier
  18/12 pipeline pilot where scratch already passed 10/12 pairs.
- Reuse has a real behavioral effect: it creates both Wins and Losses rather than merely adding
  provenance markers.
- Benefits are heterogeneous by website. Shopping and Admin are currently positive; GitLab and
  Map are negative.
- Routed trajectories are shorter, but end-to-end cost is not yet measured because routing tokens
  and the router LLM call are outside `trajectory.info.api_calls`.
- The current result supports studying contract/routing quality, not claiming an accuracy gain.

## Important design lessons

1. **Primitive contract owns site semantics.** Stable site-specific parsing and units belong in
   the primitive output contract; task-specific filtering, aggregation, and subjective judgment
   stay in the workflow/task layer.
2. **Exposure is an intervention.** A provenance marker or copied function does not prove runtime
   use; retrieval can anchor strategy even when code is not directly called.
3. **Skip matters.** Irrelevant material must be rejected. `adapt` is not automatically safe, and
   the current Losses require per-case attribution.
4. **One library per website.** Shared are the schema, updater, and retriever—not catalog content.
5. **No runtime dependency in MVP.** Vendoring is the simplest maintainable point; executable
   primitives, shared imports, dependency management, and replay gates belong to the release plan.

## Work in progress after the pushed MVP

The working tree currently explores an evidence-gated updater: every proposed primitive cites a
verbatim capability-specific code span from each source workflow, an independent judge checks
semantic support/redundancy, and one-source candidates are graded `single_source` rather than
pretending to be cross-template shared. These changes and their experimental library variants are
not part of commit `421eb94` and should not yet be treated as the frozen formal condition.

## Artifact paths

- Frozen split: `evals/webarena/splits_32_24/manifest.json`
- Site splits: `evals/webarena/splits_32_24/{shopping,gitlab,shopping_admin,map}.json`
- Train results: `evals/webarena/train_32_results/<site>/`
- Gold-admitted manifests: `evals/webarena/train_32_admitted/`
- Frozen site libraries: `evals/webarena/site_libraries_32_24/<site>/`
- Test result records: `evals/webarena/test_24_results/<site>/`
- Full run artifacts/logs: `evals/webarena/{train_32_runs,test_24_runs}/<site>/`
- Earlier 18/12 robustness pilot: `evals/webarena/test_12_results/README.md`
- MVP design: `docs/skill_factory/cross_task_primitive_mvp.md`
- Release design: `docs/skill_factory/cross_task_primitive_release.md`
- Decisions and open review items:
  `docs/skill_factory/cross_task_primitive_decisions.md` and
  `docs/skill_factory/cross_task_primitive_review_queue.md`

## Questions for mentor sync

1. Should the main claim target overall random-distribution accuracy, or capability-conditional
   reuse while keeping the random split as the robustness result?
2. Is a tied accuracy result with materially shorter agent trajectories sufficient evidence to
   pursue cost-aware routing, once router tokens/wall-clock are instrumented?
3. Should `single_source` primitives be exposed as synthesis hints, or remain quarantined until a
   second independent template confirms them?
4. For the next ablation, should we compare scratch vs raw workflow vs distilled workflow vs
   primitives vs full workflow-first routing?
