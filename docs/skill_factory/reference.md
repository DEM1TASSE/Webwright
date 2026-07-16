# Reference — verification, parameters, components, backend

[← back to the module README](../../src/webwright/skill_factory/README.md)

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

**Verification decides a skill's grade, not just its existence.** Every skill carries one of
three, and they are three different claims — `reference` is *tested and failed*, which is not
what `unverified` says:

|               | `executable` | `reference` (`--on-fail reference`) | `unverified` (`--verify off`) |
|---------------|--------------|--------------------------------------|-------------------------------|
| what happened | the replay ran and reproduced the recorded answers | the replay ran and it **failed** | **no replay ran** — nobody looked |
| cost to build | higher & slower: N replays × up to `--draws` × `--verify-rounds` distillation calls | the draws it spent failing | one distillation call |
| what it buys  | **run it directly** — plain python/playwright, no webwright, no model, cron-able | a **prior for the agent**: exact selectors, URLs, param shapes, fallbacks it reads and reuses | the same prior, with less known about it |
| trust         | proved | **known** not to reproduce its own answers | unknown — might be fine, might not |
| refining      | incremental refines must pass **regression replay** of the stored training examples (`replays.json`); a verified skill is never overwritten by an unverified refine | refined freely — no execution promise to protect | refined freely |

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

The commands, by what you already have: `init` a need → `build` a spec → or `learn` runs you
already have. `update` is the manual, manifest-driven path.

### `python -m webwright.skill_factory init "<need>"`

| flag | default | meaning |
|---|---|---|
| `-o`, `--out` | `skill.yaml` | where to write the drafted spec |
| `--rows` | 3 | how many blank instance rows to leave for you |

One LLM call. Drafts the template, the `start_url` (a guess — check it), and the verify mode it
judges the task needs; never the values.

### `python -m webwright.skill_factory build <spec.yaml>`

Solves the spec's instances, then hands them to `learn`. Everything in the spec's `build:` block
can be overridden here; machine-specific things are flags only, so the spec stays committable.

| flag | default | meaning |
|---|---|---|
| `--library` | `library` | library directory to grow |
| `-c`, `--config` | — | webwright model config for the AGENT (repeatable). It reads a yaml, **not** the env vars |
| `--jobs` | 1 | solve N instances at once — [see below](#--jobs-n--solving-in-parallel) |
| `--outputs` | `<spec dir>/build_outputs` | where solves are written; also what you point `learn` at to retry |
| `--dry-run` | off | print the plan (substituted tasks, policy, what would be solved) and stop |
| `--yes` | off | skip the confirmation before spending agent time |
| `--verify`, `--verify-rounds`, `--draws`, `--on-fail`, `--chunk`, `--golds` | from the spec's `build:` block, else `learn`'s defaults | override the spec |

### `python -m webwright.skill_factory learn <runs_dir>`

| flag | default | meaning |
|---|---|---|
| `--library` | `library` | library directory to grow |
| `--golds` | — | JSON `{task_id: gold_answer}` → gold gate instead of self_verify |
| `--chunk` | 25 | runs per LLM grouping call |
| `--dry-run` | off | print the grouping plan, change nothing |
| `--verify` | `strict` | replay bar: `strict` = reproduce recorded answers, `shape` = non-empty + schema-shaped (live data), `off` = skip |
| `--verify-rounds` | 2 | repair rounds **within one candidate** — its failures are fed back and it is re-distilled |
| `--draws` | 2 | **independent** candidates before giving up — a draw can simply come out brittle, and a fresh one often lands where repairing the bad one won't. Stops at the first that verifies |
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

### `--jobs N` — solving in parallel

Each solve takes 10-30 minutes and they don't depend on each other, so they can overlap. `N` is
any number you like; the default is `1`, meaning one after another.

```bash
--jobs 1     # the default — one at a time, output streams to your terminal
--jobs 3     # three at once — wall clock drops to roughly the slowest one
--jobs 10    # more than you have instances just means "all of them"
```

With `N > 1` each solve writes to `build_outputs/solve_NN.log` instead of interleaving on your
terminal, a progress line every 30 s shows the step each one is on, and each prints its result as
it finishes.

The real ceiling isn't the flag — it's the site. Too many browsers from one IP and you get
throttled or soft-blocked, which shows up as *your* solves failing when it's the site pushing
back, and a throttled page can even poison a training answer. **3-5 is a safe place to start**;
this box runs 3 against Google Flights and Amazon without trouble.

Parallelism only speeds up the solving half. `learn` — distil, then replay each instance in a
browser — is serial, so `--jobs` won't shorten those 5-13 minutes.
