# Held-out evaluation of an agent-built primitive library

24 cross-template held-out tasks from `splits_32_24`, primitive arm only, run 2026-08-12 at
concurrency 8. The consumer side is unchanged — the frozen scratch plan and contract-checked
local patches already on this branch. The only thing swapped is the library.

## Result

| arm | correct | mean steps |
|---|---:|---:|
| scratch (reused from `formal_32_24_audited_v4_results`) | 14/24 | 15.8 |
| primitive, scripted library (`audited_site_library_v2`) | 13/24 | 8.5 |
| **primitive, agent-built library** | **11/24** | **9.7** |

Paired against the scripted library on the same arm: 2 wins (113, 136), 4 losses (3, 122, 196,
225). Paired against scratch: 1 win, 4 losses, 10 both correct, 9 both wrong.

Routing: the agent library was skipped on 9 tasks against the scripted library's 6, and adapted
on 15 against 18. Where it was skipped, 5 of 9 came out correct; where it was adapted, 6 of 15.

## What this says, and what it does not

The two primitive arms differ by two tasks on a single sample of 24, with the same consumer
side. That is a smaller gap than the run-to-run spread already measured on the build side, where
the same inputs and the same code produced 6, 7 and 8 GitLab primitives across runs. It is not
evidence that either library is better.

What both arms share is more interesting: mean steps fall from 15.8 to under 10 whichever
library is used, and both land below scratch. Whatever is costing accuracy here is in the
consumer side, not in either library — the same shape an earlier pilot recorded, where the step
reduction came entirely from tasks the primitive arm got wrong.

## Two things that would change the reading

**The scratch baseline is reused, not re-run.** It is the batch an earlier review flagged for
contamination: scratch and primitive runs shared a site-level parent directory, and task 179 was
observed reading a sibling primitive artifact and copying its id and hash into its own
`final_script.py`. 14/24 is an upper bound, and it was produced two days earlier against a
possibly different site state.

**One sample.** Every number here is a single run of 24 tasks. The build side varies by two
primitives across identical runs; the evaluation layer can only vary more.

## A discarded first attempt

The first run of this evaluation was thrown away. `cross_task_eval.py` does not put its own
interpreter on PATH, so the agent's bash resolved `python3` to `/usr/bin/python3`, which has no
playwright. 22 of 24 runs concluded the browser was unavailable and fell back to `curl` with
HTML parsing, scoring 7/24. The results in this directory come from a re-run that exports the
venv's bin directory first; no run in it reports an unavailable browser.

The same defect had already been fixed on the build side — `skill_agent/runner.py` puts the
driver's interpreter first for exactly this reason — and was not checked for here until the
numbers looked wrong enough to inspect a trajectory.

## Contents

- `<site>/task<id>_primitive.json` — per-task result: score, steps, route decision, retrieved
  primitives, and which primitive code the final script incorporated
- `summary.json` — the table above, the pairings, and the caveats in machine-readable form

Run workspaces and trajectories are not included; they are 137 MB.

## Reproducing

```bash
export PATH=/path/to/venv/bin:$PATH          # the defect above
PYTHONPATH=src:. python evals/webarena/cross_task_eval.py run <task> primitive \
    --split evals/webarena/splits_32_24/<site>.json \
    --candidate-library skill_agent/examples/generated \
    --scratch-first --strict-arm-isolation --timeout 900
```
