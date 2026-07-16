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
| `--jobs` | 1 | solve N instances at once; more than you have means all of them. N > 1 sends each solve to `build_outputs/solve_NN.log` and ticks progress every 30 s. The ceiling is the site, not the flag — too many browsers from one IP gets you throttled, which reads as your solves failing. 3-5 is safe. Only solving parallelises; `learn` is serial |
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
| `--verify` / `--verify-rounds` / `--draws` / `--on-fail` | `off` / 2 / 2 / `reject` | as above (off by default: benchmark sites may need credentials) |

### `python -m webwright.tools.skill_use`

| flag | meaning |
|---|---|
| `--task` | the task text to match against the library |
| `--library` | library directory (or env `SKILL_LIBRARY_ROOT`) |
| `--output` | also write the JSON verdict to this file |

### Environment variables

#### Two models, two doors to the same settings

There are two separate LLMs in play, and they're configured differently:

* **the agent's model** drives the browser — the solves inside `build`, and any Webwright run.
  You point it somewhere with **a yaml**: `-c model.yaml`.
* **the module's model** does the thinking around the browser — `init` drafts your spec, `learn`
  groups runs and distils skills, `skill_use` answers "can this skill help?". You point it
  somewhere with **env vars**.

Both are the same class underneath (`webwright/models/openai_model.py`), so both really only need
two settings — *which model* and *what URL*:

| the setting | agent's model | module's model |
|---|---|---|
| which model | `model_name:` in the yaml | `SKILL_MODEL_NAME`, else `OPENAI_MODEL`, else `gpt-4o` |
| what URL | `openai_endpoint:` in the yaml | `SKILL_MODEL_ENDPOINT`, else `OPENAI_ENDPOINT`, else `https://api.openai.com/v1/responses` |

That's the whole story: `llm.py` reads the env vars and builds the *same config* the yaml spells
out by hand. `SKILL_MODEL_NAME` and `OPENAI_MODEL` are not two things — they set one field, and
`SKILL_MODEL_*` wins. Two names exist so you can send distillation to a different place than
whatever else on your machine already reads `OPENAI_*`; if you don't care, set only `OPENAI_*`.

**The agent's model does not read any of these env vars** — nothing outside `llm.py` reads them.
So on a custom gateway, set it in **both** doors, or your solves go to `api.openai.com` while
everything else uses your gateway. `build` warns when only one is set.

#### Every variable

| var | read by | meaning |
|---|---|---|
| `OPENAI_API_KEY` | **both models** | the key — this is the one genuinely shared var |
| `OPENAI_ENDPOINT` | the module's model | custom gateway. **The FULL request URL** — `https://gateway.example/api/responses`, not `.../api`. A base path fails |
| `OPENAI_MODEL` | the module's model | which model the module's calls use |
| `SKILL_MODEL_ENDPOINT`<br>`SKILL_MODEL_NAME` | the module's model | the same two settings, higher priority (see above) |
| `SKILL_MODEL_CLASS` | the module's model | a non-OpenAI backend. Defaults to `openai` |
| `SKILL_MODEL_TIMEOUT` | the module's model | seconds per call. Defaults to 600 — distilling a skill emits ~16k tokens, and the model's own 120 s default cuts it off mid-file |
| `SKILL_LIBRARY_ROOT` | `skill_use` | default for `--library`, so the agent doesn't need the path in its prompt |
| `WORKSPACE_DIR` | every generated skill | where a skill writes `agent_response.json`, its log and screenshots. Defaults to the cwd, which is why the docs `cd` to a scratch dir before running one |
| `MODEL_CFG` | `examples/quickstart.sh` only | which yaml that script passes as the agent's model. `build` takes `-c` instead |

Using the module as a library rather than a CLI? `configure_llm(model)` hands it a model object
directly and every var above is ignored — that's how a running agent gives the module its own
backend.
