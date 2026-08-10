# Cross-template site primitives: experiments, analysis, and updated pipeline

Date: 2026-08-10
Branch: `cross-task-primitives`

[中文版本](cross_template_primitive_experiment_and_pipeline_2026-08-10_zh.md)

## 1. What is being evaluated

The target setting is **cross task-template reuse within the same website**. A library is built from
gold-admitted workflows on a website, then evaluated on tasks from held-out templates on that same
website.

The unit distinction is:

- A **workflow** is a complete, standalone solution for one task template. It retains full code.
- A **primitive** is a reusable, site-specific acquisition or parsing operation, such as listing
  GitLab commits or parsing a Magento review detail page.
- Task-specific filtering, comparison, ranking, aggregation, semantic decisions, and final answer
  formatting remain in the workflow/task layer.
- For the MVP, retrieved primitive code is vendored into the generated standalone script. It is
  synthesis material, not a runtime package dependency.

## 2. Experiments must not be conflated

### 2.1 Earliest 24-task experiment: mixed routing, not primitive-only

Artifacts:

- [Summary](../../evals/webarena/test_24_results/summary.json)
- [Result README](../../evals/webarena/test_24_results/README.md)

This experiment compared scratch against a **mixed router**. Its treatment arm was:

| Route | Tasks | Meaning |
|---|---:|---|
| `workflow:adapt` | 13 | A related full workflow was supplied as an adaptation prior. |
| `primitive:adapt` | 3 | Site primitives were supplied. |
| `primitive:skip` | 8 | The router supplied no reusable material. |

Therefore its treatment result must be called `mixed routed`, not `primitive`.

| Arm | Correct | Accuracy | Mean steps |
|---|---:|---:|---:|
| Scratch | 10/24 | 41.7% | 17.08 |
| Mixed routed | 10/24 | 41.7% | 12.83 |

The paired outcomes were 3 wins, 3 losses, 7 both-correct, and 11 both-wrong. This run showed that
routing changed behavior and reduced recorded steps, but it did not isolate the contribution of
primitives because most non-skip treatment tasks used full workflows.

### 2.2 Previous primitive-only 24-task pilot

Artifacts:

- [Summary](../../evals/webarena/primitive_only_24_results/summary.json)
- [Runs](../../evals/webarena/primitive_only_24_runs/)

This experiment disabled workflow retrieval and compared scratch with primitive retrieval.

| Arm | Correct | Accuracy | Mean steps |
|---|---:|---:|---:|
| Scratch rerun | 14/24 | 58.3% | 15.79 |
| Primitive-only | 10/24 | 41.7% | 12.96 |

Primitive routing produced 17 `adapt`, 2 `use`, and 5 `skip` decisions. Primitive-source code was
detected in 16 final scripts. The paired result was 0 wins, 4 losses, 10 both-correct, and 10
both-wrong. On this run the primitive arm did not improve accuracy.

#### Control-arm contamination

The 14/24 scratch score is not a valid clean baseline. Scratch and primitive runs shared a visible
site-level parent directory. Agents were allowed to inspect the workspace, and at least tasks 57,
179, 189, and 362 exposed sibling primitive artifacts to the scratch trajectory. Task 179 explicitly
read `task179_primitive.primitive_retrieval.json` and the sibling primitive run, then copied primitive
IDs, hashes, and source markers into its own final script.

Exposure was not uniformly beneficial: task 179 changed from correct in the earlier scratch run to
incorrect after exposure. Other task changes also include ordinary sampling variation. Consequently,
14/24 cannot be interpreted as either a pure scratch score or as a four-point gain caused by
primitives. A formal paired rerun requires arm-isolated workspaces.

## 3. Why mean steps decreased

In the primitive-only pilot, total steps decreased from 379 to 311, a reduction of 68. The reduction
did **not** come from successful paired tasks:

| Outcome category | Pairs | Scratch steps | Primitive steps | Difference |
|---|---:|---:|---:|---:|
| Both correct | 10 | 141 | 141 | 0 |
| Scratch correct, primitive wrong | 4 | 82 | 54 | -28 |
| Both wrong | 10 | 156 | 116 | -40 |

Thus all aggregate step reduction came from tasks whose primitive result was wrong. The primitive
often shortened site acquisition by supplying a direct endpoint, selector, or parser, but the agent
then stopped before resolving the remaining semantic or completeness gap.

Representative cases:

- Task 154, `14 -> 7`, correct to wrong: geocoding and OSRM made route acquisition immediate, but
  did not solve place disambiguation and destination selection.
- Task 243, `22 -> 11`, correct to wrong: admin authentication and review operations accelerated
  acquisition, while the required join/filter/completeness behavior remained incomplete.
- Task 122, `30 -> 16`, correct to wrong: retrieved review material anchored the strategy even though
  the final script did not incorporate the functions. The agent stopped without reproducing the
  scratch run's full validation.
- Task 224, `28 -> 7`, both wrong: primitives quickly returned car and foot durations, but the answer
  omitted another expected transportation mode. Scratch found more modes but emitted the wrong JSON
  shape.
- Task 205, `9 -> 19`, both correct: primitive adaptation added validation and API machinery to a
  task the scratch agent already solved cheaply from the visible commit list.

Efficiency must therefore be reported as `steps conditional on correctness`, alongside accuracy.
An unconditional mean can reward early incorrect termination. In this pilot, both-correct tasks
averaged exactly 14.1 steps in each arm.

## 4. Primitive failure mechanism

The evidence does not support the claim that site primitives are intrinsically useless. It exposes
a boundary and integration problem:

1. Primitives are effective at **objective site acquisition**: login, endpoint construction,
   navigation, stable extraction, and typed parsing.
2. Cross-template tasks often differ in the part after acquisition: semantic selection, exhaustive
   traversal, record joining, ranking, aggregation, and output contracts.
3. Earlier prompts made supplied material salient enough to anchor the whole strategy. A partial
   primitive was treated as a complete plan.
4. A primitive could return plausible data without proving that the current task's acceptance
   conditions were satisfied.
5. Provenance markers measured code presence, not whether the primitive was executed or caused the
   final answer. Retrieval exposure alone can alter behavior.

The design principle is therefore: **a primitive may replace only a declared local acquisition
step; it must not replace the scratch solution's uncovered semantics.** Missing fields, incomplete
pagination, exceptions, or failed acceptance checks trigger the original scratch method for that
step rather than `NOT_FOUND_ERROR` or early submission.

## 5. Updated pipeline relative to the previous pilot

The current v4 pipeline adds the following controls.

### 5.1 Audited site-library construction

- Inputs are gold-admitted workflow scripts, grouped per website.
- Incremental update decisions are `ADD`, `UPDATE`, or `NO_CHANGE/SKIP`.
- Every update records the source workflow/template and supporting code evidence for auditability.
  Evidence may support parameterized generalization; it is not required to be a byte-identical
  implementation of the generalized primitive.
- After incremental updates, one `KEEP`/`MERGE`/`SPLIT` consolidation pass removes overlap, repairs
  granularity, and organizes methods into feature classes.
- Each website is rendered as one package file with a root site class and feature modules/classes,
  for example `GitLabSite.auth`, `GitLabSite.issues`, and `GitLabSite.commits`.
- Snapshots preserve per-batch updates, the pre-consolidation pool, consolidation proposal,
  validation, coverage, final index, and final package.

The current four-site audited snapshot was built from 17 gold-admitted workflows and contains:

| Site | Active primitives |
|---|---:|
| Shopping | 5 |
| GitLab | 8 |
| Shopping Admin | 4 |
| Map | 2 |

See the [audited build walkthrough](audited_cross_template_site_library_2026-08-10.md) and the
[library snapshot](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/).

### 5.2 Stronger primitive contracts

- Primitives return typed objective facts rather than untyped DOM blobs where possible.
- `owns` and `does_not_own` explicitly separate site behavior from task semantics.
- Input/output contracts describe which fields are available to a consumer.
- The router must enumerate remaining gaps instead of presenting partial coverage as complete.
- Source-answer hard-coding and unsupported capability expansion remain invalid.

### 5.3 Scratch-first local-patch routing

The previous pilot exposed primitives before the agent committed to a solution shape. The updated
flow first creates a task-only plan while library material is hidden. Retrieval then maps primitives
only onto named scratch steps:

```text
task
  -> frozen scratch plan
  -> metadata retrieval and use/adapt/skip decision
  -> approved local patches: scratch_step -> primitive
  -> preserve uncovered scratch steps
  -> execute each patch with acceptance checks
  -> on partial/failed patch, run that step's scratch fallback
  -> vendor accepted code into standalone final_script.py
  -> evaluate final answer
```

The prompt now states that primitive failure is not evidence that the requested website fact does
not exist. It also forbids redesigning or reordering the rest of the frozen scratch plan merely
because a primitive was retrieved.

### 5.4 Retrieval behavior

Retrieval is intentionally two-stage:

1. Rank compact metadata: capability, ownership boundary, contracts, site/module, provenance, and
   supported patterns.
2. Inject complete code only for selected primitives.

The router chooses:

- `use`: selected primitives cover the required site operations, while the task layer still owns
  task semantics and formatting;
- `adapt`: primitives cover one or more useful local steps but leave explicit gaps;
- `skip`: supplied material does not materially advance the scratch plan.

Workflow retrieval remains a separate ablation. It must not be silently mixed into a run reported
as primitive-only.

## 6. Complete build-to-evaluation workflow

```text
Gold-admitted train workflows, partitioned by site
  -> batch incremental updater
       ADD / UPDATE / NO_CHANGE
       audit each workflow contribution
       save batch snapshots
  -> pre-consolidation primitive pool
  -> consolidate + organize
       KEEP / MERGE / SPLIT
       validate workflow coverage and contracts
       render one object-oriented site package
  -> freeze library and manifest
  -> held-out cross-template task
       create scratch-only plan before retrieval
       retrieve primitive metadata from same-site library
       decide use / adapt / skip
       fetch full code for selected primitives
       declare local patches, gaps, and acceptance checks
       vendor accepted methods into standalone workflow
       preserve scratch fallbacks
  -> WebArena evaluator
  -> paired report
       accuracy first
       wins/losses/both-correct/both-wrong
       steps conditional on correctness
       route and incorporation diagnostics
```

For a clean experiment, scratch and primitive arms must run in mutually inaccessible workspaces.
The current directory convention still permits sibling visibility, so absence of observed reads is
not sufficient for a formal claim. The rerun protocol should physically separate arms and audit
trajectory file access before aggregation.

## 7. Current interpretation and next measurement

The earliest result establishes only that mixed reuse changed strategies; it does not isolate
primitives. The previous primitive-only pilot establishes that the old injection protocol could
retrieve and incorporate primitives, but it produced no wins and four losses, and its scratch arm
was contaminated. Neither is the final efficacy number.

The updated pipeline tests a narrower hypothesis: whether correct site primitives can safely replace
specific acquisition steps while preserving the consumer's scratch semantics. The next report must
come from an arm-isolated paired run using the frozen four-site library. Until that finishes, the
honest status is:

- library construction and retrieval mechanisms are implemented and tested;
- primitive coverage and provenance are auditable;
- the previous accuracy result is negative under the old integration protocol;
- the updated integration protocol does not yet have a clean, completed WebArena number.
