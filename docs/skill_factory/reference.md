# Reference — verification, parameters, components

[← back to the module README](../../src/webwright/skill_factory/README.md)

## Verification and grades

Two gates check different things. The **input gate** decides whether a solve is trustworthy enough
to build from; the **output gate** decides whether the distilled skill actually runs. Each has
three levels:

| gate | what it asks | levels (strict → loose) | what it decides |
|---|---|---|---|
| **input** | is this solve's answer trustworthy? | `gold` (match a known answer) → `self_verify` (shape + non-empty + the agent's own "I succeeded"; passes wrong-but-plausible answers, so use `gold` when correctness matters) → `none` | whether a solve becomes **material** for a skill |
| **output** | can the skill reproduce the answer with no model? | `strict` (reproduce the recorded answer) → `shape` (non-empty + schema-shaped, for drifting answers) → `off` (no replay) | the skill's **grade**, below |

The output gate spends two nested budgets, `--draws` independent candidates each repaired up to
`--verify-rounds` rounds; if none reproduce the recorded answers, nothing lands.

Whichever level the output gate ran at becomes the skill's **grade**:

| | `executable` | `reference` (`--on-fail reference`) | `unverified` (`--verify off`) |
|---|---|---|---|
| what happened | replay ran and reproduced the answers | replay ran and it **failed** | **no replay ran** |
| what it buys | **run it directly**: plain python/playwright, no model, cron-able | a **prior for the agent**: exact selectors, URLs, param shapes it reads and reuses | the same prior, but untested: might run standalone, might be broken |
| trust | proved | **known** not to reproduce its answers | unknown |
| refining | incremental refines must pass **regression replay** (`replays.json`); a verified skill is never overwritten by an unverified refine | refined freely | refined freely |

`unverified` (`--verify off`) skips replay entirely. Use it when a skill can't be replayed, because
the data has drifted or the page moved, but you want to keep it anyway. It's an escape hatch, not a
grade to aim for; normal runs land `executable` or `reference`.

Why code even at `reference` grade, versus a natural-language note: the selectors, URLs and param
shapes are verbatim-copyable into the agent's next script, individual primitives often still run
when the whole skill doesn't, and a reference skill is one repair away from executable. And
`reference` pulls its weight in practice, the WebArena numbers in
[Results](../../src/webwright/skill_factory/README.md#-results) were produced by a reference-grade
library. The flights skill in the [Quickstart](quickstart.md), by contrast, reruns an unseen route
standalone, which is what `executable` buys.

## All parameters

The main path is three commands: `init` a need → `build` a spec → or `learn` runs you already
have. `update` and `skill_use` below are the manual / integration surface, not the day-to-day
path.

### `python -m webwright.skill_factory init "<need>"`

| flag | default | meaning |
|---|---|---|
| `-o`, `--out` | `skill.yaml` | where to write the drafted spec |
| `--rows` | 3 | how many blank instance rows to leave for you to fill (these become the `instances:` in the spec) |

One LLM call. Drafts the template, the `start_url` (a guess, check it), and the verify mode it
judges the task needs. Never the values.

### `python -m webwright.skill_factory build <spec.yaml>`

Solves the spec's instances, then hands them to `learn`. Everything in the spec's `build:` block
can be overridden here; machine-specific things are flags only, so the spec stays committable.

| flag | default | meaning |
|---|---|---|
| `--library` | `library` | library directory to grow |
| `-c`, `--config` | — | webwright model config for the AGENT (repeatable). It reads a yaml, **not** the env vars |
| `--jobs` | 1 | solve N instances at once; more than you have means all of them. N > 1 sends each solve to `build_outputs/solve_NN.log` and ticks progress every 30 s. The ceiling is the site, not the flag: too many browsers from one IP gets you throttled, which reads as your solves failing. 3–5 is safe. Only solving parallelises; `learn` is serial |
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
| `--verify-rounds` | 2 | repair rounds **within one candidate**: its failures are fed back and it is re-distilled |
| `--draws` | 2 | **independent** candidates before giving up. A draw can simply come out brittle, and a fresh one often lands where repairing the bad one won't. Stops at the first that verifies |
| `--on-fail` | `reject` | failed verification: `reject` (runs stay retryable) or `reference` (lands as a labeled prior; never overwrites an existing skill) |

### Manual / integration path

#### `python -m webwright.skill_factory.update`

The manifest-driven path (see [manual.md](manual.md)). Use it when you're assembling batches by
hand rather than from a spec.

| flag | default | meaning |
|---|---|---|
| `--manifest` | required | `{template, runs:[{dir, admit(bool, REQUIRED), params, verdict, site, output_schema, answer?, credentials?}]}` |
| `--library` | required | library directory |
| `--verify` / `--verify-rounds` / `--draws` / `--on-fail` | `off` / 2 / 2 / `reject` | as above. `--verify` is `off` by default here because benchmark sites may need credentials; `--verify-rounds` and `--draws` only take effect once you turn `--verify` on |

#### `python -m webwright.tools.skill_use`

The call the agent makes to query the library at solve time.

| flag | meaning |
|---|---|
| `--task` | the task text to match against the library |
| `--library` | library directory (or env `SKILL_LIBRARY_ROOT`) |
| `--output` | also write the JSON verdict to this file |

### Environment variables

**There are two models here, and they're configured differently.** This trips everyone up once,
including us, so it's worth the sentence:

| | who runs it | what it does | how you point it somewhere |
|---|---|---|---|
| **the module's model** | `init`, `learn`, `build`'s learn half, `skill_use` | groups runs, distils skills, answers "can this skill help?" | **env vars**, the `OPENAI_*` below |
| **the agent's model** | the solves inside `build`, and any Webwright run | drives the browser | **a yaml**, `-c model.yaml`. It does **not** read these env vars |

So on a custom gateway you set it in **both** places, or the solves quietly go to `api.openai.com`
while everything else uses your gateway. `build` warns when you've done one and not the other.

| var | read by | meaning |
|---|---|---|
| `OPENAI_API_KEY` | every LLM call, both models | the key |
| `OPENAI_ENDPOINT` | the module's model (`llm.py`) | custom gateway. **The FULL request URL**, e.g. `https://gateway.example/api/responses`, not `.../api`. A base path fails |
| `OPENAI_MODEL` | the module's model | model name for the module's calls |
| `SKILL_MODEL_ENDPOINT` / `SKILL_MODEL_NAME` / `SKILL_MODEL_CLASS` / `SKILL_MODEL_TIMEOUT` | the module's model | the same four settings, but only for this module; use them to send distillation somewhere other than the agent. Fall back to `OPENAI_*`. Class defaults to `openai`, timeout to 600 s (a 16k-token distillation is slow) |
| `SKILL_LIBRARY_ROOT` | `skill_use` | default for `--library`, so the agent doesn't need the path in its prompt |
| `WORKSPACE_DIR` | every generated skill | where a skill writes `agent_response.json`, its log and screenshots. Defaults to the cwd, which is why the docs `cd` to a scratch dir before running one |
| `MODEL_CFG` | `examples/quickstart.sh` only | which yaml that script passes as the agent's model. `build` takes `-c` instead |

## Components

The module's files and what each one does, for anyone reading or extending the code.

| file | role |
|---|---|
| `library.py`  | `Skill` + `Library(root)`: on-disk skills (`<id>/skill.py` + `meta.json`) |
| `retrieve.py` | `retrieve(task, library)` → ranked `Candidate`s (relevance) |
| `decide.py`   | `decide(task, candidates)` → `Decision(verdict, skill_id, reason)` (utility: use/adapt/skip) |
| `gate.py`     | `gate(result, method=gold\|self_verify\|none)` → admit? (keeps wrong solves out) |
| `update.py`   | `evolve(traces, library)`: grow on the existing library (add / adapt-refine / keep); `_refine` parameterizes and decomposes into primitives, incrementally improving an existing skill |
| `llm.py`      | `configure_llm(model)` + `llm()`: **backend-agnostic** via Webwright's `Model` abstraction; a bare CLI builds the model from `SKILL_MODEL_NAME`/`SKILL_MODEL_ENDPOINT` (or `OPENAI_*`) env, no hardcoded endpoint/key |
| `prompt.py`   | `with_skill_hint(prompt, task, library)`: non-invasive task-prompt hint (manual reuse path) |

**Backend.** Backend-agnostic. Either call `configure_llm(model_config_or_Model)` once in-process,
or set `SKILL_MODEL_NAME` / `SKILL_MODEL_ENDPOINT` (falling back to `OPENAI_*`) so a bare tool
invocation uses the same backend as the running agent. No gateway or key is hardcoded.
