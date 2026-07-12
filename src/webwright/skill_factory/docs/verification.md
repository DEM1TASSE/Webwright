# Verification and grades

[← back to the module README](../README.md)

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

