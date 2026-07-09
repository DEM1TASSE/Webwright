# Reproducing the WebArena numbers

The skills README claims, for 10 task templates across 3 sites:

```
                          tasks  correct  accuracy  avg steps
held-out  WITH library       20       14     70.0%       14.7
held-out  from scratch       20       11     55.0%       17.1
train     WITH library       30       26     86.7%       13.7
train     from scratch       30       23     76.7%       15.9
```

This directory contains everything needed to check those numbers — at two depths.

## Depth 1: audit the recorded run (no setup, no cost)

`results/` is the per-task record of the exact run behind the table: one JSON per solve
with the task id, the answer the agent produced, the gold score, the step count, and the
agent's skill verdict. Aggregate it yourself:

```bash
python reproduce.py table --results results
```

That command computes the table above from the raw records — the module README rounds
86.7/76.7 down to 86/76. Spot-check any row against the public
[webarena-verified](https://github.com/microsoft/webarena-verified) dataset: the `tid`
field is the public task id, and the gold answers live in the dataset.

## Depth 2: re-run the experiment (your WebArena, your model, real cost)

You need:

1. **This repo installed** — `pip install -e .` in a venv (playwright set up per the main README).
2. **A WebArena deployment** — the standard self-hosted sites (shopping_admin, gitlab, map).
   Task prompts and scoring come from [webarena-verified](https://github.com/microsoft/webarena-verified);
   follow its setup to get:
   - the dataset json (`webarena-verified.json` — tasks + golds),
   - your `verified_config.json` (maps site placeholders to **your** deployment URLs + credentials),
   - a python env with the `webarena_verified` package (used for gold scoring; pass it via
     `--eval-python` if it isn't the current interpreter).
3. **Model credentials** — `OPENAI_API_KEY`; on a custom OpenAI-compatible gateway also
   `OPENAI_ENDPOINT` and `OPENAI_MODEL` (the skills module reads these), and set the same
   endpoint/model for the *agent* in `model.eval.yaml`. The recorded run used one frontier
   model for both; expect a few points of variance from model/version drift — LLM solving
   is stochastic. The step counts and the WITH-vs-scratch *gap* are the stable signal.

Then:

```bash
export WEBARENA_DATASET=/path/to/webarena-verified.json
export WEBARENA_CONFIG=/path/to/your/verified_config.json
export OPENAI_API_KEY=...        # + OPENAI_ENDPOINT / OPENAI_MODEL on a gateway

python reproduce.py plan         # prints all ~130 commands in dependency order
./run_all.sh                     # ...or runs them sequentially (hours; parallelize per template)
python reproduce.py table        # the table, from YOUR runs
```

The flow per template: solve the 3 train tasks from scratch → `update` distills the
**gold-admitted** solves into one library skill (this is the gold gate the module README
refers to) → solve the 2 held-out tasks twice, once WITH the library and once from scratch,
and score both against gold.

**Cost warning:** 100 agent solves plus library updates — expect several hours of wall
time sequentially and real API spend. `reproduce.py` is resumable: finished tasks are
skipped, so you can stop and restart, or run templates in parallel shells.

## What's what

| file | role |
|---|---|
| `reproduce.py` | self-contained driver: solve / update / heldout / table |
| `run_all.sh` | runs the whole plan sequentially |
| `model.eval.yaml` | eval overrides for the agent model (+ where to point a gateway) |
| `results/` | sanitized per-task records of the recorded run (the numbers' provenance) |

`tests/skills/test_eval_snapshot.py` locks the snapshot to the published numbers in CI —
if the records and the README table ever disagree, the build fails.
