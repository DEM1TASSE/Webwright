# Architecture and design rationale

[← back to the module README](../README.md)

**Why webwright makes this natural.** Webwright is a terminal/code-native agent: its actions
are code, and every solve already leaves behind a working script. The agent's exhaust is
already code — turning it into skills is a byproduct, not an extra instrumentation layer.
It complements `crafted_cli`: where `crafted_cli` parameterizes a single task's script by
anticipating what might vary, `update.refine` parameterizes **across multiple verified
solves** — the differences actually observed between instances become the parameters.

**One solve isn't a skill yet.** A single task's script is correct but narrow — it solves
*that* instance. So the update step aggregates multiple verified solves of the same task
template: values that differ across instances become parameters, patterns that recur become
shared primitives. The merged skill is often better than any single solve it came from —
different runs' strategies become fallbacks, and what settles into the library isn't a
click-path but the best algorithm the solves discovered (our commit-counting skill distilled
UI exploration into `git clone + git log`).

**The library keeps growing — safely.** A self-evolving loop feeds later solves back in: new
templates add skills, new solves refine existing ones in place (working functions kept), and
skills with nothing new stay byte-identical. Growth never breaks what already works.



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

