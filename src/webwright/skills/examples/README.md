# Examples — what a skill library looks like, and what reuse buys you

This directory is what the module README points at whenever it says "see examples": two
real, checked-in skill libraries you can read and run (nothing is hand-written — both are
verbatim pipeline output), the wrapper script the Quickstart uses, and filled-in copies of
every input file the manual pipeline asks you to write.

```
examples/
├── learned_library/                  # produced by `skills learn` from 3 real solves (n_solves=3):
│   └── what_is_the_cheapest_flight…/ #   the Quickstart artifact — Google Flights, FIVE params
│                                     #   (origin/destination city+code, date); unseen route
│                                     #   SEA->DEN standalone in ~30 s, matched the agent's answer
├── example_library/                  # a library with one skill, exactly as evolve wrote it
│   └── how_many_commits_did_user_make_period_in_the_cur/
│       ├── skill.py                  #   the executable skill (126 lines)
│       └── meta.json                 #   the catalog card retrieval reads
├── taskspec.example.json             # input for running the skill directly
├── tasks.example.json                # input for the batch pipeline (README step 6)
└── batch.example.json                # a filled manifest (README step 2)
```

## The learned library — the Quickstart loop, already run and checked in

`learned_library/` is the exact artifact the README Quickstart produces. Three from-scratch
solves of "cheapest one-way flight" on Google Flights (SEA→JFK, SFO→BOS, LAX→ORD; 13, 26
and 18 agent steps — airport comboboxes and date pickers are genuinely fiddly) were grouped
by `python -m webwright.skills learn` into one template with **five** lifted parameters:

```json
{
  "template": "What is the cheapest flight from {{origin_city}} ({{origin_code}}) to {{destination_city}} ({{destination_code}}) on {{date}} (one-way)? ...",
  "signature": { "params": ["origin_city", "origin_code", "destination_city", "destination_code", "date"],
                 "call": "python skill.py taskspec.json" },
  "n_solves": 3
}
```

On an unseen route it runs standalone — real playwright driving the live site, no model:

```bash
cd learned_library/what_is_the_cheapest_flight_from_origin__7725080
cat > taskspec.json <<'EOF'
{"params": {"origin_city": "Seattle", "origin_code": "SEA", "destination_city": "Denver",
            "destination_code": "DEN", "date": "2026-08-15"},
 "output_schema": {"type": "array", "items": {"type": "string"}}}
EOF
python skill.py taskspec.json    # ~30 s -> {"retrieved_data": ["Frontier", "$68"]} (live price)
```

Measured on that unseen route, minutes apart (full table and reading in the module README's
Quickstart): from scratch 17 steps / 8.9 min; with the library 15 steps / 5.2 min;
standalone ~30 s with no model — all three answers identical.

`tests/skills/test_learned_example.py` locks the aggregation properties for every skill in
the directory (n_solves ≥ 3, parameters actually lifted, code compiles) in CI.

## What a skill looks like

`example_library/` is real output too — produced by `update.evolve` during the WebArena
evaluation, lightly curated. One template = one skill = one self-contained directory. The `meta.json` is the catalog card
(what `retrieve` sees); the `skill.py` is what the agent reads and reuses:

```json
{
  "template": "How many commits did {{user}} make {{period}} in the current repository?",
  "site": "gitlab",
  "signature": { "params": ["user", "period"], "call": "python skill.py taskspec.json" },
  "n_solves": 2
}
```

The interesting part: the two train solves this was distilled from solved the task **through the
web UI** (opening commit lists, filtering, paging). What `evolve` settled into the library is a
**better algorithm** the solves discovered — clone the repo and count with git directly:

```python
def count_commits_with_git(repo_dir, author, start_dt, end_dt, branch="main"):
    cmd = ["git", "-C", str(repo_dir), "log", branch,
           "--since", start_dt.strftime("%Y-%m-%d %H:%M:%S"),
           "--until", end_dt.strftime("%Y-%m-%d %H:%M:%S"),
           "--author", author, "--pretty=format:%H"]
```

`user` and `period` are function parameters. `period` accepts the two shapes observed across the
train instances (full month names): `"on January 5th 2023"` and
`"between start of February 2023 and end of May 2023"`.

**Where the skill's coverage ends — visibly.** Feed it a period shape it never saw (say
`"in Jan 2023"`) and it raises `Unsupported period format` cleanly instead of guessing. This is
the parameter-coverage boundary the eval doc discusses: on the real held-out run with exactly
that unseen shape, the *agent* read this source, kept the git-clone core, and inlined the dates
itself — reuse degrades to adaptation, not to a wrong answer.

## What reuse buys you (measured, WebArena held-out tasks)

Held-out = unseen instances of the template; WITH = agent may query the library; BASE = from
scratch. Same model, same budget.

| held-out task (template)               | BASE (scratch)     | WITH library      |
|----------------------------------------|--------------------|-------------------|
| commits by {user} in {period} (gitlab) | correct, 33 steps  | correct, **10 steps** |
| commits by {user} in {period} (gitlab) | correct, 19 steps  | correct, **10 steps** |
| walking+driving route times (map)      | **wrong**, 21 steps| **correct**, 8 steps  |
| walking+driving route times (map)      | **wrong**, 19 steps| **correct**, 10 steps |
| all reviews with <=3 stars (shopping)  | **wrong**, 31 steps| **correct**, 13 steps |

Aggregate over 10 templates x 3 sites (20 held-out instances): **70% vs 55% accuracy, 14.7 vs
17.1 steps** (per-task records + rerun driver: [`evals/webarena/`](../../../../evals/webarena/)).
Two kinds of wins: tasks that get *cheaper* (33 -> 10) and tasks that get
*solvable* (wrong -> correct). Honest counterpoint: on tasks the agent already solves in a few
steps, querying the library costs more than it saves — reuse pays on expensive-to-explore tasks.

## Try it

**1. Run the skill directly — no LLM, no agent needed:**

```bash
cd src/webwright/skills/examples
cat > taskspec.json <<'EOF'
{"params": {"user": "Jane Doe", "period": "on January 5th 2023"},
 "start_url": "https://gitlab.com/<group>/<repo>",
 "credentials": null,
 "output_schema": {"type": "array", "items": {"type": "number"}}}
EOF
python example_library/how_many_commits_did_user_make_period_in_the_cur/skill.py taskspec.json
cat agent_response.json    # {"task_type": "RETRIEVE", "status": "SUCCESS", "retrieved_data": [N], ...}
```

Point it at any repo you can clone; fill any author/period. This is the whole point of a *code*
skill: it runs without a model in the loop.

**2. Ask the tool whether the library helps a task (one LLM call pair):**

```bash
export OPENAI_API_KEY=...
python -m webwright.tools.skill_use \
  --task "How many commits did Alice make in March 2024 in the current repository?" \
  --library "$PWD/example_library"
# -> {"verdict": "use", "skill_id": "how_many_commits_...", "source_path": "...", ...}
```

**3. Full agent reuse:** follow "How to use" in the module README, pointing `with_skill_hint`
at `examples/example_library`.

## Example inputs for the batch pipeline

`tasks.example.json` and `batch.example.json` are filled-in versions of the files the module
README's steps 2 and 6 ask you to write — copy, replace values, go.
