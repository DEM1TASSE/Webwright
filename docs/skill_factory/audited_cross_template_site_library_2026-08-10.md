# Audited cross-template site library: build flow and 2026-08-10 snapshot

This document records the MVP pipeline used to build one primitive package per WebArena site and
links the complete auditable snapshot produced from the frozen 32-train/24-test protocol.

## Snapshot

The build consumes only the 17 gold-admitted train workflows. It produced 19 candidate primitives:

| Site | Gold workflows | Primitives | Package | Metadata | Review |
|---|---:|---:|---|---|---|
| Shopping | 4 | 5 | [package.py](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/shopping/final_candidate/package.py) | [index.json](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/shopping/final_candidate/index.json) | [review.md](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/shopping/final_candidate/review.md) |
| GitLab | 7 | 8 | [package.py](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/final_candidate/package.py) | [index.json](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/final_candidate/index.json) | [review.md](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/final_candidate/review.md) |
| Shopping Admin | 3 | 4 | [package.py](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/shopping_admin/final_candidate/package.py) | [index.json](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/shopping_admin/final_candidate/index.json) | [review.md](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/shopping_admin/final_candidate/review.md) |
| Map | 3 | 2 | [package.py](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/map/final_candidate/package.py) | [index.json](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/map/final_candidate/index.json) | [review.md](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/map/final_candidate/review.md) |

Machine-readable aggregate: [summary.json](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/summary.json).

These packages are candidate synthesis material, not promoted runtime dependencies. A selected
method is copied into a standalone workflow; historical workflows do not import the package.

## Build pipeline

```text
gold-admitted workflows
  -> per-workflow capability extraction
  -> batch ADD / UPDATE / SKIP reconciliation
  -> quality and coverage gate with regeneration
  -> unclassified primitive pool
  -> one KEEP / MERGE / SPLIT consolidation pass
  -> deterministic feature-class and package rendering
```

### 1. Gold admission and deterministic batching

Only evaluator-passing train workflows enter the builder. Workflows are grouped by site, sorted by
template/task ID, and shuffled with the recorded seed before bounded batching. The snapshot records
the order under each site's `workflow_order.json`.

### 2. Per-workflow extraction

The extractor reads one workflow without seeing the library and enumerates reusable website
operations. It keeps site navigation, selectors, endpoints, pagination and stable parsing in the
primitive boundary; task filtering, aggregation, ranking and answer formatting remain workflow
logic. Local git/filesystem operations are not website primitives.

Concrete instance values may be generalized into parameters. Source evidence is lightweight
attribution: it identifies a gold workflow and explains what was generalized. It is not required
to reproduce source code byte-for-byte. The deterministic checks require valid workflow/template
attribution, a source reference and explanation, and reject obvious answer leakage.

Each extraction directory retains `input.json`, every `attempts.json`, `extraction.json`, and
`validation.json`.

### 3. Batch reconciliation

All extracted candidates in a batch are reconciled against a compact index of the current pool.
The only updater operations are:

- `ADD`: create a complete candidate method and contract;
- `UPDATE`: replace an existing method while preserving capability identity and core contract;
- `SKIP`: decline an unsupported or already-covered candidate with attribution.

Every workflow and extracted candidate must be accounted for. Candidate code must parse, expose one
public method, use the site component's `self.page`, return typed facts rather than DOM/page blobs,
and preserve the primitive/workflow boundary.

An independent quality/coverage prompt reviews each proposal. A rejected proposal and its exact
errors are fed back to the builder, which regenerates a complete proposal; the manager never edits
primitive code itself.

### 4. Consolidate and organize

After all batches, one site-wide pass must consume every primitive exactly once:

- `KEEP`: retain the method and assign a feature;
- `MERGE`: combine genuinely duplicate/overlapping capabilities;
- `SPLIT`: divide a method that mixes independent acquisition boundaries.

Feature names become composition components such as `projects`, `issues`, `orders`, `reviews`,
`places`, and `routes`. Sharing a feature does not force methods to merge. The consolidation input,
attempts, proposal, validation, and exact-coverage report are retained under each site's
`consolidation/` directory.

### 5. Deterministic package rendering

The class manager does not call an LLM. It renders one feature class per group and a small site
facade. For example, GitLab becomes:

```text
GitLabSite
  commits       -> GitLabCommits
  contributors  -> GitLabContributors
  issues        -> GitLabIssues
  members       -> GitLabMembers
  projects      -> GitLabProjects
```

## Concrete GitLab trace

GitLab is the richest example in this snapshot.

### Inputs and extraction

Seven gold workflows entered one batch. Extraction proposed 11 candidates:

- task 306/template 321: repository commits;
- task 317/template 324: branch contributors;
- task 350/template 298: members and personal-project search;
- task 789/template 328: project search, project availability and visible projects;
- task 172/template 289: dashboard projects and overview metrics;
- task 175/template 310: dashboard issues and issue detail state;
- task 785/template 316: skipped because it used local `git clone`/`git log`, not a website/API
  acquisition.

See [workflow order](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/workflow_order.json)
and the [extraction directories](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/extractions/).

### Reconciliation and quality repair

The batch converged after six proposals. Earlier attempts exposed duplicate attribution, overly
broad project-link heuristics, and unsupported search-result claims. The final proposal retained
eight supported primitives and rejected three project-search candidates whose source parsers could
not reliably distinguish project records from generic GitLab links.

- [Batch input](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/batches/batch_000/input.json)
- [All attempts and validation feedback](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/batches/batch_000/attempts.json)
- [Accepted proposal and attribution](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/batches/batch_000/proposal.json)
- [Pre-consolidation pool](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/pre_consolidation/primitive_pool.json)

### Consolidation

The site-wide pass kept all eight methods and assigned five features. It did not merge methods:
list/detail operations within the same feature have different acquisition contracts.

- `commits`: `list_repository_commits`
- `contributors`: `list_repository_branch_contributors`
- `members`: `list_project_members`
- `projects`: availability, dashboard listing, overview metrics
- `issues`: dashboard listing and detail state

See the [consolidation proposal](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/consolidation/proposal.json),
[validation](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/consolidation/validation.json),
and [coverage](../../evals/webarena/site_libraries_32_24_audited_20260810_v4/gitlab/consolidation/coverage.json).

## New-task use pipeline

The frozen library is consumed as follows:

```text
new cross-template task
  -> draft a task-only scratch plan before library exposure
  -> retrieve against compact primitive metadata
  -> decide use / adapt / skip
  -> inject complete code only for selected primitives
  -> replace concrete acquisition sub-operations
  -> retain task filtering/ranking/formatting in the workflow
  -> check patch acceptance conditions
  -> fall back to the original scratch step on failure
```

Selected code is vendored into the generated standalone script. A short acyclic patch chain may
connect outputs to later scratch steps, but the library itself has no primitive runtime dependency
graph.

## Reproduction entry points

- Builder: [`evals/webarena/build_audited_primitive_library.py`](../../evals/webarena/build_audited_primitive_library.py)
- Build implementation: [`audited_primitive_build.py`](../../src/webwright/skill_factory/audited_primitive_build.py)
- Retriever/patcher: [`audited_primitive_retrieve.py`](../../src/webwright/skill_factory/audited_primitive_retrieve.py)
- WebArena runner: [`cross_task_eval.py`](../../evals/webarena/cross_task_eval.py)

The snapshot was generated with seed `20260810`, batch size 8, explicit gateway model
configuration, and the frozen admitted manifest `evals/webarena/train_32_admitted/by_site.json`.
