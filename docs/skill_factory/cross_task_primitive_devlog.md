# Cross-Task Primitive Development Log

## 2026-08-05

- Branch: `cross-task-primitives` in `DEM1TASSE/Webwright`.
- Phase 0:
  - Added a frozen Map split with 12 held-out tasks across 6 unseen templates.
  - Split validation checks task IDs, template disjointness, site, retrieve type, and evaluator set.
  - Added two manually curated oracle snippets. They are pilot material, not automatically
    promoted primitives; only task 248 currently supplies an observed gold-admitted source.
  - Confirmed task 248 completes browser execution and passes `AgentResponseEvaluator` (score 1).
- Phase 1:
  - Added site-scoped bounded retrieval, deterministic/LLM ranking, browser-state
    `requires/provides` completion and ordering, full-code vendoring prompt, provenance markers,
    and retrieval records.
  - Added opt-in `route --primitive-site`; exact runnable workflow remains first, otherwise the
    experiment uses primitives or scratch and does not mix related-workflow adaptation.
- Phase 2:
  - Added structured `ADD / MODIFY / SPLIT / ARCHIVE / NO_CHANGE` proposals.
  - Catalog writes occur only after static and gold-provenance checks. Low-confidence proposals
    enter the review queue without blocking later operations.
- Verification:
  - `pytest -q tests/skill_factory`: 126 passed.
  - `cross_task_eval.py validate`: valid.
  - Oracle catalog snippets pass catalog AST/self-containment validation.
- Environment:
  - Map is healthy and retrieve-only tests do not mutate it.
  - A full reset attempt was slow and left GitLab stopped because of a remote container-name
    conflict; Shopping and Forum health checks also timed out. This does not block the Map pilot.

## Phase 0/3 frozen pilot result

- Completed all 24 runs: 12 held-out tasks × (`scratch`, `oracle`), across 6 unseen templates.
- Scratch: 6/12 correct; oracle: 7/12 correct.
- Pairwise: 2 Wins, 1 Loss, net +1; both Wins came from template 68.
- Average agent steps: scratch 15.6; oracle 17.2.
- Primitive code markers appeared in 11/12 oracle final scripts. The original pilot prompt did
  not produce `primitive_usage.json`, so declared-use coverage is 0/12; the prompt now requests
  it for future runs.
- Pre-registered gate: **INCONCLUSIVE / GO=false** because net gain is below +2 and Wins cover
  only one template. No learned primitive is promoted and catalog size remains 2 → 2.
- Authoritative machine-readable result:
  `evals/webarena/cross_task_results/summary.json`.

## Experiment commands

Use:

```bash
PYTHONPATH=src /home/t-demiwang/project/webwright/.venv/bin/python \
  evals/webarena/cross_task_eval.py run <task_id> scratch|oracle \
  --dataset /home/t-demiwang/project/Code-Web-Agent/webarena-verified/assets/dataset/webarena-verified.json \
  --config /home/t-demiwang/project/Code-Web-Agent/verified_config.json \
  --eval-python /home/t-demiwang/project/Code-Web-Agent/.venv-eval/bin/python \
  --model-config /home/t-demiwang/project/Code-Web-Skills/code/configs/model_gateway_54.yaml
```

## 2026-08-07: 18/12 train-test protocol

- Frozen protocol: 3 train templates and 2 test templates per site, 2 instances per template.
  Across Shopping, GitLab, and Shopping Admin this is 18 train tasks and 12 paired test tasks.
- Formal split has train/test only. Development case studies are performed inside train.
- Added real `routed` harness support and aggregate reporting:
  workflow metadata → adapt/skip; on skip, primitive metadata → use/adapt/skip; full primitive
  code is fetched only after use/adapt.
- Fixed null completion detection: a complete `NOT_FOUND_ERROR` artifact with
  `retrieved_data=null` no longer runs until timeout.
- Infrastructure failures (`score=null`) are recorded separately and excluded from accuracy.
- Generated-only frozen candidate library currently contains one admitted primitive per site,
  each supported by two gold-admitted train templates. No hand-written primitive was used.
- Gold-admitted train workflows were also distilled into six unverified/reference workflow
  priors so the formal routed arm exercises workflow-first behavior.
- Train E2E checks:
  - Admin task213: workflow adapt, score 1.0, 18 steps, no primitive mixed in.
  - GitLab task135: primitive adapt, score 0, 11 steps; scratch also score 0, 16 steps.
  - Shopping task384: primitive adapt, score 0, known subjective quality boundary failure.
- Split manifest: `evals/webarena/splits_18_12/manifest.json`.
- Frozen candidate library: `evals/webarena/frozen_library_18_12`.

## 2026-08-07: frozen test result

- The remote WebArena reset completed; the subsequent health check returned Shopping 200,
  Shopping Admin 200, Forum 200, Wikipedia 200, Map 200, and GitLab 302.
- The frozen library remained byte-identical after all test runs (21/21 files).
- Formal paired result on 12 template-disjoint test tasks:
  - scratch: 11/12 (91.7%);
  - routed: 10/12 (83.3%);
  - delta: -8.3 percentage points;
  - 0 Wins, 1 Loss, 10 both-correct, 1 both-wrong;
  - mean steps: 13.17 scratch versus 13.92 routed;
  - routed decisions: 6 adapt, 6 skip.
- Shopping Admin task1 failed to emit a complete response in both arms within the bounded run and
  one retry, so both are counted as failures rather than excluded.
- A harness bug discovered during retry cleanup was fixed: timeout now terminates the complete
  spawned process group, not only the CLI parent.
- Final report: `evals/webarena/test_12_results/README.md`.
- Machine-readable summary: `evals/webarena/test_12_results/summary.json`.
- Verification: frozen library valid; `pytest -q tests/skill_factory`: 146 passed.
