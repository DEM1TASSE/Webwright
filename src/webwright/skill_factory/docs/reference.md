# Reference — verification, parameters, components, backend

[← back to the module README](../README.md)

## Verification and grades

**Validation-gated — exactly as strong as the gate you give it.** Every solve passes an
admission gate before it can enter the library. With gold answers (benchmarks — this is what
our WebArena numbers used) the gate is real supervision: wrong answers never get in. The
default `self_verify` gate checks shape, non-emptiness, and the agent's **own final report**
(a run that reported `NOT_FOUND_ERROR` is rejected — the agent itself didn't believe it) —
it filters garbage and self-admitted failures, **not wrong-but-plausible answers the agent
believed**. Pass `--golds` to `learn`, or bring your own judge, when correctness matters.
The gate also has an **output side**: a skill must run **standalone** on its own training
taskspecs and reproduce the recorded answers before it may enter the library (no model in the
loop; up to `--verify-rounds` build attempts, then rejected). For task families whose answers
are live data (prices, listings), `--verify shape` relaxes the comparison to non-empty +
schema-shaped; `--verify off` skips replay entirely.

**Verification decides a skill's grade, not just its existence** (`--on-fail reference`):

|                 | `executable` (verified)                          | `reference`                          |
|-----------------|--------------------------------------------------|--------------------------------------|
| the bar         | replays its training taskspecs standalone, reproduces the answers | failed that bar |
| cost to build   | higher & slower: N replays + up to `--verify-rounds` distillation calls | one distillation call |
| what it buys    | **run it directly** — plain python/playwright, no webwright, no model, cron-able | a **prior for the agent**: exact selectors, URLs, param shapes, fallbacks it reads and reuses |
| refining        | incremental refines must pass **regression replay** of the stored training examples (`replays.json`); a verified skill is never overwritten by an unverified refine | refined freely — no execution promise to protect |

Why code even at reference grade (vs. natural-language notes): the selectors, URLs and param
shapes are **verbatim-copyable** into the agent's next script, individual primitives often
still run even when the end-to-end skill doesn't, and a reference skill is one repair away
from executable — prose is none of these.

Honest footnote: our WebArena numbers predate this gate — that library was effectively
all-reference (a later standalone audit: only 3/10 skills replayed clean), and it still
delivered **+15pp held-out accuracy**. That is the evidence that reference-grade priors help
an agent; the flights quickstart's three-way consistency is the evidence for the executable
grade.

## Components

| file | role |
|---|---|
| `library.py`  | `Skill` + `Library(root)`: on-disk skills (`<id>/skill.py` + `meta.json`) |
| `retrieve.py` | `retrieve(task, library)` → ranked `Candidate`s (relevance) |
| `decide.py`   | `decide(task, candidates)` → `Decision(verdict, skill_id, reason)` (utility: use/adapt/skip) |
| `gate.py`     | `gate(result, method=gold\|self_verify\|none)` → admit? (keeps wrong solves out) |
| `update.py`   | `evolve(traces, library)`: grow on the existing library — add / adapt-refine / keep; `_refine` parameterizes + decomposes into primitives, incrementally improving an existing skill |
| `llm.py`      | `configure_llm(model)` + `llm()`: **backend-agnostic** via Webwright's `Model` abstraction; a bare CLI builds the model from `SKILL_MODEL_NAME`/`SKILL_MODEL_ENDPOINT` (or `OPENAI_*`) env — no hardcoded endpoint/key |
| `prompt.py`   | `with_skill_hint(prompt, task, library)`: non-invasive task-prompt hint |

## Backend

Backend-agnostic. Either `configure_llm(model_config_or_Model)` once in-process, or set
`SKILL_MODEL_NAME` / `SKILL_MODEL_ENDPOINT` (falling back to `OPENAI_*`) so a bare tool invocation
uses the same backend as the running agent. No gateway or key is hardcoded.

## All parameters

### `python -m webwright.skill_factory learn <runs_dir>`

| flag | default | meaning |
|---|---|---|
| `--library` | `library` | library directory to grow |
| `--golds` | — | JSON `{task_id: gold_answer}` → gold gate instead of self_verify |
| `--chunk` | 25 | runs per LLM grouping call |
| `--dry-run` | off | print the grouping plan, change nothing |
| `--verify` | `strict` | replay bar: `strict` = reproduce recorded answers, `shape` = non-empty + schema-shaped (live data), `off` = skip |
| `--verify-rounds` | 2 | total build attempts (first + repairs) before giving up |
| `--on-fail` | `reject` | failed verification: `reject` (runs stay retryable) or `reference` (lands as a labeled prior; never overwrites an existing skill) |

### `python -m webwright.skill_factory.update`

| flag | default | meaning |
|---|---|---|
| `--manifest` | required | `{template, runs:[{dir, admit(bool, REQUIRED), params, verdict, site, output_schema, answer?, credentials?}]}` |
| `--library` | required | library directory |
| `--verify` / `--verify-rounds` / `--on-fail` | `off` / 2 / `reject` | as above (off by default: benchmark sites may need credentials) |

### `python -m webwright.tools.skill_use`

| flag | meaning |
|---|---|
| `--task` | the task text to match against the library |
| `--library` | library directory (or env `SKILL_LIBRARY_ROOT`) |
| `--output` | also write the JSON verdict to this file |

### Environment variables

| var | used by | meaning |
|---|---|---|
| `OPENAI_API_KEY` | all LLM calls | API key |
| `OPENAI_ENDPOINT` / `OPENAI_MODEL` | learn, skill_use | custom gateway; the endpoint is the FULL request URL (e.g. `https://gateway.example/api/responses`), not a base path |
| `SKILL_MODEL_NAME` / `SKILL_MODEL_ENDPOINT` / `SKILL_MODEL_CLASS` / `SKILL_MODEL_TIMEOUT` | module LLM | overrides for the module's model (fall back to `OPENAI_*`) |
| `SKILL_LIBRARY_ROOT` | skill_use | default library path |
| `WORKSPACE_DIR` | generated skills | where a skill writes its artifacts (default: cwd) |
| `MODEL_CFG` | examples/quickstart.sh | model yaml for the agent in solve/full modes |
