# `webwright.skills` — a memory / skill-library module for Webwright

Turn solved tasks into **reusable, executable code skills**, retrieve and judge them at solve
time, gate what enters the library, and grow the library incrementally. A self-evolving loop:

```
solve  --(gate: gold | self_verify)-->  admit  --(evolve: refine + parameterize + primitives)-->  library
  ^                                                                                                   |
  |  skill_use tool: retrieve + decide (use / adapt / skip)  <--------------------------------------- +
```

This is the missing **reuse + accumulation** layer: it consumes the `final_script.py` every
Webwright solve already produces (plain or crafted mode — both work), accumulates skills across
tasks, judges when a prior skill applies, and improves skills as more solves arrive — with a gate
so wrong solves don't pollute the library. It complements `crafted_cli`: where `crafted_cli`
parameterizes a single task's script by anticipating what might vary, `update.refine`
parameterizes **across multiple verified solves** — the differences actually observed between
instances become the parameters.

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
   Manifest schema and a full walkthrough: see **How to use** below.

## How to use (end-to-end)

The library grows **offline** from batches of solved tasks, and is consumed **at solve time** by
the agent. Tasks are provided **manually** today — you pick which tasks to solve and batch. The
current focus is **same-template generalization**, so feed several instances of the SAME template
(3+ instances with different parameter values works well): `refine` aligns them, and exactly what
differs between instances becomes the skill's parameters — more instances, wider generalization.
(Planned: bootstrap — automatically expand one seed task into multiple instances.)

### 1. Solve a few instances of a template (normal Webwright runs)

```bash
python -m webwright.run.cli main \
  -t "How many commits did kilian make to a11yproject on 3/1/2023?" \
  --task-id t132_a --start-url http://gitlab.example.com -o outputs \
  -c base.yaml -c model_openai.yaml
```

Each run leaves a directory containing `final_script.py` (the executable solve) and
`agent_response.json` (the answer). Repeat for 2–3 more instances of the same template with
different values (another user / repo / date).

### 2. Gate the solves, write the manifest

Judge each run (`gate(result, method="gold")` against a known answer, or `method="self_verify"`
without one) and write one manifest per batch:

```jsonc
// batch.json
{
  "template": "How many commits did {{user}} make to {{repo}} on {{date}}?",
  "runs": [
    {
      "dir": "outputs/t132_a_20260703_120000",   // run dir; final_script.py is read from it
      "admit": true,                             // gate verdict — false rows NEVER enter the library
      "params": {"user": "kilian", "repo": "a11yproject", "date": "3/1/2023"},
      "verdict": "skip",                         // how the run used the library: skip = solved from
                                                 // scratch; use / adapt = reused a skill
                                                 // (adapt triggers refine-back into the skill)
      "site": "gitlab",
      "output_schema": ["number"]                // required shape of retrieved_data
      // "answer": optional — read from the run dir's agent_response.json when omitted
    },
    { "dir": "outputs/t132_b_20260703_121500", "admit": true,
      "params": {"user": "gao", "repo": "2019", "date": "4/6/2023"},
      "verdict": "skip", "site": "gitlab", "output_schema": ["number"] }
  ]
}
```

`params` is each instance's concrete values — this is what powers generalization: `refine` aligns
the runs, keeps what is identical as the skeleton, and exposes exactly these differing values as
the skill's arguments.

### 3. Build / evolve the library

```bash
export OPENAI_API_KEY=...                        # backend key (never stored by the module)
# optional — defaults to OPENAI_MODEL / OPENAI_ENDPOINT:
export SKILL_MODEL_NAME=gpt-5.4 SKILL_MODEL_ENDPOINT=https://api.openai.com/v1/responses
python -m webwright.skills.update --manifest batch.json --library ./library
```

Prints a changelog: `{"added": [...], "adapt_refined": [...], "use": [...], "dropped_wrong": n}`.
Re-run with later batches any time — a new template **adds** a skill, new solves for an existing
template **refine it in place** (keeps its working functions), templates with no new traces are
left untouched. Batches may mix templates.

### 4. Reuse at solve time

```python
from webwright.skills import with_skill_hint
prompt = with_skill_hint(prompt, task=task_text, library="./library")
```

```bash
SKILL_LIBRARY_ROOT=./library python -m webwright.run.cli main -t "$prompt" ...
```

The hint tells the agent to query the library first; the agent runs the `skill_use` tool, gets
`{verdict, skill_id, source_path, how_to_reuse}`, reads the skill source, and reuses it
(use = as-is with new parameter values, adapt = reuse the core + change the last step,
skip = solve from scratch).

### 5. Run a skill directly (optional)

Every skill is also a standalone script: it reads a `taskspec.json` (parameters at run time) and
writes `agent_response.json`:

```bash
cat > taskspec.json <<'EOF'
{"params": {"user": "byte", "repo": "empathy-prompts", "date": "4/2/2023"},
 "start_url": "http://gitlab.example.com", "credentials": null,
 "output_schema": ["number"]}
EOF
python library/how_many_commits_did_user_make_to_repo_on_date/skill.py taskspec.json
cat agent_response.json
```

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
