# Web Skill Factory version index

This branch is the **all-code handoff**, not a frozen benchmark arm. It combines the
best validated primitive implementation with the official WebArena split/runner and
portable WebVoyager/Odysseys support.

Its Git history also joins the primitive-router, skill-build-agent, Odysseys,
WebVoyager, skill-factory and skill-library experiment lines with an archival `ours`
merge. The merge preserves every historical commit without pretending that mutually
exclusive implementations can coexist in one runtime tree.

## BEST — use this version

Branch: [`web-skill-factory-best`](https://github.com/DEM1TASSE/Webwright/tree/web-skill-factory-best)

Frozen commit: `100a0e3`

Pipeline label: **V12 direct primitive pipeline**

Generated library: V11 audited library consumed by the V12 router/consumer.

Authoritative paired WebArena T2 result:

| Arm | Success | Mean agent steps |
|---|---:|---:|
| Scratch | 93/156 (59.6%) | 13.20 |
| Primitive | 100/156 (64.1%) | 11.90 |
| Delta | **+4.5 pp** | **-9.8%** |

Why it is BEST: this is the strongest version with a complete, isolated, same-run
156-task paired evaluation and a machine-readable summary. Use it for reproduction,
paper numbers, and demonstrations.

Key files:

- `evals/webarena/primitive_v12_pipeline_review_zh-CN.md`
- `evals/webarena/reuse_split_v1_eval_results_v12_mixed_paired/summary.json`
- `evals/webarena/primitive_rt_v1_library_v11_public/`

## DEV — promising, not the reported best

These versions were developed after inspecting the 156-task set. They are development
evidence and must not be presented as untouched test results.

| Version | Purpose | Status |
|---|---|---|
| V13 | Late-bind downstream operators after candidate discovery | DEV subset only |
| V14 | Preserve entity/type/scope constraints | DEV safety improvement |
| V15 | Scratch-first plan and complete fallback gate | DEV subset only |
| V16 | Recover checkable named-entity recall | DEV subset only |
| V17 | Frozen scratch-first full-run configuration | DEV/freeze; no authoritative promoted summary |
| V18b | Structured fact/postcondition development | DEV subset |
| V18c | Contract-closure freeze | DEV/freeze; no completed authoritative full-156 summary |

Local-only raw evidence is recorded in
`primitive_router_iteration_log_zh-CN.md` and the corresponding versioned run/result
directories in the private handoff package.

## HISTORICAL / ABLATION

| Version | Meaning |
|---|---|
| V4 | Early audited primitive build used by the first formal arm |
| V5–V8 | Early library/router and parallelization iterations |
| V9 | Full baseline: 62/156 primitive vs 65/156 scratch; motivated guard work |
| V10 | Population-completeness guard development; not promoted |
| V11 | Typed atomic library, behavior smoke, runtime acceptance and Full4 |
| Workflow/raw-script arms | Granularity and reuse-source ablations, not the primitive BEST arm |

## INVALID — never report as results

- V10 initial E2E attempt that fell back to the public endpoint and failed with 401.
- V12 Full5 attempt started with the wrong 59-task split.
- V12 pre-mixed attempt that labeled Navigate tasks as Retrieve.
- V14 initial batch missing `PYTHONPATH=src`.
- PATH/curl-degraded and cross-arm-directory-contaminated early pilots.
- Concurrency stress runs: infrastructure measurements, not model-quality results.

## Code layout in this branch

- `src/webwright/skill_factory/`: build, retrieve, update, validation and library code.
- `evals/webarena/`: primitive/workflow builders, routers, evaluation scripts and compact evidence.
- `skills/official-webarena/`: official task split, deployment adapter, runner and evaluator wrapper.
- `evals/webvoyager/`: WebVoyager pipeline and audited-build support.
- `evals/odysseys/`: Odysseys runner and rubric export.
- `tests/`: unit and pipeline tests.

Historical implementations remain reachable through Git history and named experiment
branches. They are intentionally not copied into parallel `v5/`, `v6/`, ... source trees,
because that would create multiple editable copies of the same modules.
