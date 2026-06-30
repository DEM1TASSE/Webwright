# `webwright.skills` — a memory / skill-library module for Webwright

Turn solved tasks into **reusable, executable code skills**, retrieve and judge them at solve
time, gate what enters the library, and grow the library incrementally. A self-evolving loop:

```
solve  --(gate: gold | self_verify)-->  admit  --(evolve: refine + parameterize + primitives)-->  library
  ^                                                                                                   |
  |  skill_use tool: retrieve + decide (use / adapt / skip)  <--------------------------------------- +
```

This is the missing **reuse + accumulation** layer: Webwright already turns a task into a
parameterized script (`crafted_cli`); this module accumulates those across tasks, judges when a
prior skill applies, and improves skills as more solves arrive — with a gate so wrong solves don't
pollute the library.

## How it plugs into Webwright

Two touch points, **no change to the agent loop or default config**:

1. **Reuse at solve time — the `skill_use` tool.** The agent invokes it from bash, exactly like
   `self_reflection` / `image_qa`:
   ```bash
   python -m webwright.tools.skill_use --task "<the task>" --library "$SKILL_LIBRARY_ROOT"
   ```
   It returns JSON `{verdict: use|adapt|skip, skill_id, source_path, how_to_reuse}`. The agent
   reads `source_path` and reuses the skill (use = as-is, adapt = reuse core + change last step,
   skip = solve from scratch). `webwright.skills.with_skill_hint(prompt, ...)` prepends a one-line
   usage hint to the task prompt so the agent remembers to query the library first.

2. **Growth after solving — the `update` CLI.** Distill a batch of gate-passed solves into a
   library skill (offline, not in the solve loop):
   ```bash
   python -m webwright.skills.update --manifest batch.json --library ./library
   ```
   `batch.json = {"template": "...", "runs": [{"dir","admit","params", ...}, ...]}`.

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

## Gate

`gate(method=...)` is the **admission** check (independent of the solving agent — not the same as
`self_reflection`, which is the agent's own completion condition):
- `gold` — compare against a known answer (benchmarks); strongest.
- `self_verify` — invariant only (non-empty + shape); weak placeholder when no gold exists. It does
  not check *correctness*. Note: `self_reflection` cannot serve as the gate — `require_self_reflection_success`
  makes it always `predicted_label==1`, so it would admit everything (agent grading itself).
- `none` — admit all (demos).

## Backend

Backend-agnostic. Either `configure_llm(model_config_or_Model)` once in-process, or set
`SKILL_MODEL_NAME` / `SKILL_MODEL_ENDPOINT` (falling back to `OPENAI_*`) so a bare tool invocation
uses the same backend as the running agent. No gateway or key is hardcoded.

## Results (summary)

Validated with this module (full data + analysis live in the companion research repo, not here):
- **Real website (public GitHub, read-only):** end-to-end loop works — two repos solved from
  scratch → `update` distilled a parameterized skill → a held-out repo solved by reusing it
  (agent called `skill_use`, verdict `use`, answer correct).
- **Incremental growth:** a second batch improves the existing skill in place (keeps the working
  functions, adds robustness) rather than rewriting it.
- **Gate prevents pollution:** a wrong solve is dropped and never enters the library.
- **Reuse value is task-dependent:** step savings are modest on easy tasks (query overhead ≈ the
  exploration it saves) and larger on harder tasks with more exploration to skip.
