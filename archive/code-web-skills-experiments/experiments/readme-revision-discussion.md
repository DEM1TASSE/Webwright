# README / Quick Start revision — running discussion

Open items for the module README (`src/webwright/skill_factory/README.md`) on the
`skill-library` branch. Each item records the problem, why it matters, the options, and
where the decision stands. Add new items at the bottom.

---

## 1. §2 "Bring the agent in" — wrong place, and the example doesn't motivate it

**Status:** open — deciding between the options below.

### The problem

Quick Start currently runs:

1. **Run a learned skill** — the flights skill, standalone, no model, ~40 s
2. **Bring the agent in** — `ask` / `solve`, *on that same flights skill*
3. **Build your own skill** — `init` → fill → `build`, or `learn`

Two things are wrong with §2:

- **The example defeats its own point.** §1 has just shown that skill running end to end
  with no model. A reader arriving at §2 asks the obvious question: *if the program already
  runs by itself, why would I ask an agent to use it?* The section demonstrates the
  integration surface but gives no reason to want it.
- **It comes before the reader has a library.** §2 reuses a pre-made skill before §3 has
  shown how a skill is created. Reuse is more natural *after* build: you now have a library,
  so here is how the agent draws on it.

### Why you actually bring the agent in

Two cases, and neither is what §2 currently shows:

1. **The skill can't run on its own.** When replay fails, the skill lands at `reference`
   grade — it is not trusted to execute standalone, but the agent can still read its
   selectors, URLs and parameter shapes as a prior. This is the case the grade system was
   built for, and the README never demonstrates it.
2. **The task is outside the skill's parameter range.** The new task varies something the
   skill doesn't take as a parameter, so it can't be applied directly. The agent takes the
   source and reworks it for the task in hand. This is exactly the `adapt` verdict from
   `skill_use` — and `adapt`, not `use`, is where the agent earns its keep.

### Options

- **A — keep the flights example, add variants that create the two cases.** e.g. a
  `reference`-grade skill to show case 1, and a task just outside the skill's parameters
  (a different trip shape, or an extra field the skill doesn't return) to show case 2.
  Keeps one example family across the whole Quick Start; costs new fixtures/runs.
- **B — use a different example for §2** that naturally needs the agent. Costs a second
  example family for the reader to hold in mind.
- **Ordering, independent of A/B — move the agent section after build.** Flow becomes:
  run a ready-made skill → build your own → the agent reuses/adapts what you built.
  Counter-consideration: `ask` is currently a cheap early proof that the integration is one
  call (~10 s). If it moves after build, the reader pays build time before seeing the
  integration at all. A middle path is to keep a one-line `ask` teaser early and move the
  substantive *adapt* demonstration after build.

### Leaning

Option **A + reorder**: the failure modes are already first-class in the system (`reference`
grade, `adapt` verdict), so demonstrating them costs no new concepts — and it converts §2
from "here is an API" into "here is when you need it." Decision pending.

---

## 2. `ask` — is it a step at all? (verified: it is what `solve` already does)

**Status:** open — leaning "remove it as a numbered step, keep the command."

### The finding

`ask` is not a separate capability. It is the agent's own internal call, run by hand:

- `examples/solve_with_library.sh` builds the agent prompt with `with_skill_hint(...)`.
- `prompt.py:15` — that hint injects this exact line into the agent's prompt:
  `python -m webwright.tools.skill_use --task {task} --library {library}`
- `quickstart.sh ask` runs *that same command* directly.

So **`ask` is included in `solve`**: during a solve the agent queries the library itself. A
user solving a real task never runs `ask` — running it by hand only lets a human watch the
call the agent is about to make anyway.

### Why it's a problem

Quick Start numbers it like a step you perform, which misrepresents what you actually run
and pads the "getting started" path with something nobody uses standalone.

### What it is genuinely good for

One audience: **integrators**. The JSON it prints (`verdict` / `skill_id` / `source_path` /
`how_to_reuse`) is the contract another agent framework would implement against, and seeing
it costs ~10 s and one LLM call instead of a 5-minute solve. That is a real use — it just
isn't a Quick Start step.

### Options

- **A — drop `ask` from Quick Start**, keep the command. Show the JSON contract where
  integration is actually discussed (reference / integration docs). Quick Start then lists
  only what a user runs.
- **B — keep it, but reframe as an aside**, not a numbered step: a collapsed "what the agent
  sees when it queries the library" under the agent section, explicitly labelled as the
  agent's internal call rather than a user action.
- **C — remove the command entirely.** Rejected: it is the documented integration surface
  and useful for debugging retrieval ("why did it pick that skill?").

### Leaning

**A**, with the JSON contract moved to the integration docs. It removes a step users don't
take, and puts the contract where the audience that needs it is looking. This also shrinks
§2 to the part that has to be shown live: the agent adapting a skill it can't just run
(see item 1).

---

## 3. `init` makes you hand-fill the YAML — the LLM should propose the values

**Status:** open — leaning "propose values, marked as guesses."

### The friction

`init` writes a spec whose instance rows are `____` and tells you to fill them in before
`build` will do anything. That is a blank form standing between "I described my task" and
"something happened."

### The stated reason doesn't hold up

`init.py`'s docstring says it "deliberately does NOT invent the values — those are the ground
truth you own, and a wrong guessed value would quietly train the skill on the wrong answer."

That conflates two different things. The instance values decide **which instances get
solved** (inputs). The answers come from **actually solving them against the live site**
(outputs). A value the LLM proposes doesn't create a wrong answer; it creates a different —
still valid — training instance, whose answer is whatever the site says. The values are not
ground truth, so the stated rationale is a category error.

### And we're already inconsistent

The same file happily guesses `start_url` and marks it `# guessed — check it opens the right
page`. Guessing the site but refusing to guess a date is not a principle, it's an
inconsistency.

### What guessing values actually risks

1. **Invalid values → wasted solves.** A route with no nonstop flight, a product that
   doesn't exist: the solve burns agent time and returns nothing. Mitigated by `build
   --dry-run`, which prints the substituted tasks before spending anything.
2. **Too little variation → a narrower skill.** Parameters are lifted from the differences
   between instances, so if the LLM proposes three rows that share a date, that axis never
   becomes a parameter. This is the existing "vary the parameters" advice, and it applies to
   proposed values as much as to hand-written ones.

Notably, "the values aren't the ones I care about" is **not** a real risk: the skill is
parameterized, so you supply your own values when you run it. Training instances only need
to be valid and varied.

### Options

- **A — propose values by default**, written into the spec and marked as guesses exactly the
  way `start_url` already is (`# guessed — replace with your own`). Keep a `--blank` flag for
  anyone who wants the current behaviour.
- **B — keep blank by default, add `--propose-values`.** Conservative, but leaves the
  friction as the default path, which is the thing being complained about.
- **C — propose and pre-validate** each value against the site before solving. Rejected for
  now: a real check costs a page load per value, which is most of what a dry-run solve
  already tells you.

### Leaning

**A**, and fix the docstring's reasoning while we're there. The prompt should be told to
propose values that are (a) real and likely to exist on that site, and (b) varied along every
parameter, since those are the two things that actually matter. `build --dry-run` stays the
cheap check before any money is spent.

### Refinement — the count is a flag we already have

`init` already takes `--rows` (default 3); today it means "how many blank rows to leave."
Under option A it simply changes meaning to **how many instances to propose**, so no new
flag is needed:

```bash
python -m webwright.skill_factory init "<need>"            # 3 proposed instances
python -m webwright.skill_factory init "<need>" --rows 5   # 5
```

And the spec stays an ordinary file you edit: open `skill.yaml`, replace any proposed value
with the instance you actually want to run, add or delete rows. The proposal is a starting
point, not a commitment — the file, not the flag, is where you say what you want tested.

This keeps all three properties: no blank form on the happy path, an explicit knob for how
many, and full manual control for anyone who wants to hand-pick the experiments.

---

## 4. Tasks that need *your* logged-in data — two problems, one of them structural

**Status:** **deferred.** Decision: don't handle credentials for now — let the LLM propose
values and keep the path simple. Item (b) below is recorded because it's a real gap, but it is
explicitly out of scope for this revision.

Raised against item 3: if the task depends on the user's own account ("my orders", "commits
in my private repo", "my invoices"), what does a proposed value even mean?

### (a) The values are unknowable — so don't propose them

For an account-scoped task the LLM cannot invent a meaningful instance: it doesn't know your
order numbers or your repo names. Proposing values there is worse than leaving blanks,
because a plausible-looking wrong value burns a solve before you notice.

`init` already makes this kind of call: it asks the LLM to judge `drifts` and writes
`drift_reason` into the spec. The same mechanism extends — judge whether the task is
**account-scoped**, and if so leave the rows blank *with the reason written in*, instead of
proposing. So item 3's default ("propose values") becomes "propose values unless the task is
account-scoped."

### (b) The quick path can't carry credentials at all

Verified in source, and this is the bigger problem:

- `credentials` appears only in `update.py` — the manifest path (`traces_from_manifest`
  reads `r.get("credentials")`, and it flows into the taskspec used for replay).
- `learn.py` and `build.py` have **no credentials parameter whatsoever**.

So for a logged-in task the `init → build → learn` path can still *solve* (the agent drives a
browser that may already be authenticated), but the **replay-verify runs `skill.py`
standalone with no way to authenticate**. The skill fails replay and can never reach
`executable` through the quick path. Manual mode (`update --manifest` with `credentials`) is
the only route that supports it — which is exactly why manual mode exists, but the Quick
Start never says so.

### Options

- **A — document the boundary.** `init` detects an account-scoped task, leaves the rows
  blank with the reason, and points at manual mode for credentials. Cheap, honest, no code
  beyond the judgement.
- **B — carry credentials through the spec.** Add a `credentials:` block to `skill.yaml`
  that `build` passes to solves and `learn` passes into the replay taskspec, so logged-in
  tasks can reach `executable` on the quick path. This is the real fix; it needs a decision
  about where the secret lives (env var reference rather than a value in a committable
  file).
- **C — both:** A now, B as the follow-up.

### Leaning

**C.** A is needed regardless — right now a user can spend an entire build on a logged-in
task and only discover at replay that it was never going to verify. B is worth doing because
"the task you repeat" is *especially* likely to be behind a login (your dashboards, your
orders, your internal tools) — the very audience the module targets. If B lands, the
credential should be referenced by env-var name in the spec, never stored in it.

---

## 5. Fold §3.1 (`learn` from existing trajectories) into §3.2

**Status:** open — leaning "fold it in as an aside."

### The problem

§3 currently offers two co-equal ways in:

- **3.1 — you have trajectories:** point `learn` at a folder of finished runs
- **3.2 — you have a task, no runs:** `init` → fill → `build`

3.1 is presented first, as the "day-to-day path." For a new reader it is almost never the
path they can take:

1. **Most people don't have trajectories yet.** They arrived to build a skill, not with a
   folder of past solves.
2. **What they have shapes what they get.** `learn` handles a mixed batch by design — it
   groups runs by template and emits one skill per family (`update.py:358-362`), with no
   minimum count, so a family with a single run still produces a skill. The difference is
   breadth: a family with several runs gets parameters lifted from the differences between
   them; a singleton gets a narrower skill from one trace. So pointing `learn` at an old
   outputs folder isn't wrong — it just produces whatever those runs support, which for
   unrelated one-off runs is a set of narrow skills.

### It also isn't a separate concept

`build.py:41` imports `learn`, and `build.py:230` calls it: **build = solve × N + learn**.
So `learn` is build's second half, not a parallel route. Presenting it as path 3.1 splits one
idea into two entries and puts the rarer one first.

### Options

- **A — fold into 3.2 as an aside.** §3 becomes one path (`init` → `build`), with a short
  note at the end: *already have several solves of the same **task family** — one template,
  different values? skip the solving; `learn <runs_dir>` is the half of `build` that distils
  them.* Naming that precondition is what makes the shortcut work at all.
- **B — keep both, reverse the order.** Less churn, but still presents a rare path as a
  co-equal choice.
- **C — drop `learn` from Quick Start entirely**, document it only in the reference.
  Rejected: it's genuinely useful for anyone re-running distillation over runs they already
  paid for (e.g. after a rejected batch).

### Leaning

**A.** One path in Quick Start, with `learn` named where it belongs — as build's second half
and as the shortcut for people who already have runs. Worth stating what makes that shortcut
pay off: several runs of the same task family (one template, *different* values), since the
parameters come from the differences between them. It still works on anything you point it
at; that's just the case where it produces a broad skill rather than a narrow one.

---

## 6. The generated skill isn't actually runnable on its own

**Status:** open — leaning "give it real CLI flags and a useful failure."

### What happens today

`skill.py` takes exactly one positional argument: a path to a taskspec JSON.

```python
TASKSPEC_PATH = Path(sys.argv[1]).resolve()          # skill.py:19-21
TASKSPEC = json.loads(TASKSPEC_PATH.read_text(...))
PARAMS = TASKSPEC.get("params", {}) or {}
```

Measured:

- `python skill.py` → `IndexError: list index out of range` — a raw traceback, no message.
- `python skill.py --help` → `FileNotFoundError: '/tmp/--help'` — the flag is read as a path.

So to run one you must already know (1) that it wants a JSON file, (2) the exact parameter
names, and (3) that an `output_schema` key belongs in there. None of that is discoverable
from the skill itself.

### Why it matters

"A program that runs on its own — no model needed" is the headline claim of the comparison
table, and the thing that separates this from the document-based projects. It's true about
*execution*, but running one currently takes archaeology. Next to `opencli hackernews top
--limit 5` — self-describing, `--help` works, arguments declared — ours looks worse at
exactly the axis we claim as our advantage.

### We already have what's needed

- `replays.json` records the parameter names *and* a set of real, working values from
  training (e.g. `{origin_city, origin_code, destination_city, destination_code, date}`).
- `meta.json` records `output_schema` and `signature`.

So a generated CLI, a `--help`, and a copy-pasteable example can all be derived from what
the skill already ships with — no new bookkeeping.

### Options

- **A — emit real CLI flags.** The distillation knows the parameters (it lifted them), so
  the generator can emit an argparse block: `python skill.py --origin-code SEA
  --destination-code DEN --date 2026-08-15`, with `--taskspec file.json` still accepted for
  programmatic use. `--help` then lists the parameters.
- **B — fail usefully.** Keep the taskspec interface, but on a bare run print the required
  parameters and a ready-to-paste example taskspec built from `replays.json`.
- **C — a runner subcommand** (`python -m webwright.skill_factory run <skill> --origin ...`)
  that assembles the taskspec. Rejected as the primary answer: it puts the package back
  between the user and the skill, which is the opposite of "runs on its own."

### Leaning

**A + B.** A makes the standalone claim true in practice and matches how every other CLI
tool behaves; B costs almost nothing and rescues anyone who runs the file to see what it
does. Both keep the skill self-sufficient — no import of this package required to run it.

---

## 7. A dispatcher: decide "run it directly" vs "hand it to the agent"

**Status:** open — this is the missing middle tier, and two prerequisites are missing in code.

### The idea

Given a task in natural language, something should decide: is there an executable skill that
covers this? If yes, run it and return the answer. If not, hand it to the agent.

### Why this matters — and is "agent use" redundant?

Partly, yes, and that is the point. Today there are only two tiers:

- **Tier 0 — you name the skill and its parameters.** Zero model calls. But you have to know
  which skill and which params (see item 6).
- **Tier 2 — the full agent loop.** Tens of model calls, minutes.

There is nothing in between, so any task expressed in words falls to tier 2 — *even when an
executable skill already covers it*. That is where "asking the agent to use the skill" looks
redundant: for a task the skill already handles, an agent loop is enormous overkill.

The missing tier:

- **Tier 1 — one model call.** Route to the right skill *and* extract this task's parameters,
  then execute the skill deterministically. Not zero-model (turning words into parameters
  needs one call), but one call instead of a loop.

With tier 1 present, the agent is left with the cases that genuinely need it — the same two
from item 1: the skill is `reference` grade and can't execute, or the task falls outside the
skill's parameters. That makes §2 of the Quick Start honest instead of redundant.

### What's missing in code (verified)

1. **`skill_use` doesn't extract parameters.** It returns `verdict / skill_id / reason /
   call / how_to_reuse`, and `skill_use.py:62` says outright: *"USE: copy the source into
   your final_script and fill THIS task's params"* — filling them is delegated to the agent.
2. **The decision ignores `grade`.** `decide.py` judges use / adapt / skip with no reference
   to `grade` anywhere in `decide.py` or `skill_use.py`. So the layer that picks a skill has
   no idea whether that skill can run standalone (`executable`) or is only a prior
   (`reference`) — which is precisely the fact a dispatcher needs.

### Sketch

A verdict set that answers the real question:

- `run` — an `executable` skill whose parameters cover the task; params extracted; execute it
- `adapt` — a skill matches but can't be executed as-is (reference grade, or the task needs
  something outside its parameters) → the agent takes the source
- `skip` — nothing relevant → the agent solves from scratch

`run` is the new one, and it needs (1) grade to reach the decision layer and (2) parameter
extraction in the same call that already judges relevance — both cheap, since the call is
being made anyway.

### Open questions

- **Who validates the extracted parameters?** A wrong extraction runs the skill on the wrong
  input and returns a confident wrong answer. The output schema catches shape, not sense.
- **What happens when `run` fails?** Natural fallback: fall through to `adapt` and let the
  agent take over, which is the behaviour a user would expect anyway.
- **Does this belong in `skill_use`, or beside it?** `skill_use` is the agent's own call.
  A dispatcher is for the *caller* who hasn't decided whether to involve an agent at all —
  possibly a separate entry point that uses the same retrieve/decide core.

### Recommendation — split it: fix the defect now, defer the feature

Verified while assessing this: `how_to_reuse` is a **hardcoded constant** (`skill_use.py:61-63`),
identical for every skill and blind to `grade`:

```
"USE: copy the source into your final_script and fill THIS task's params;
 ADAPT: reuse its login/navigation/extraction core, change ONLY the final step."
```

So for an `executable` skill — one that could simply be executed — we instruct the agent to
**copy the source into its own script**. That is not a missing feature; it is the direct cause
of the failure observed on 2026-07-17, where a solve looped re-emitting a 700-line skill into
one response until it was truncated. The agent wasn't being stupid; it was following the
instruction we handed it.

**Do now (defect fix, small):** let `grade` reach the decision layer and branch
`how_to_reuse`:

- `executable` → *run it:* `python <source_path>/skill.py taskspec.json`, with the params
- `reference` / `unverified` → *read it as a prior:* reuse the core, change the final step

This collapses most of the agent's work on in-range tasks and removes the inline-rewrite
pathology, without adding any new concept.

**Defer (feature):** the full tier-1 dispatcher — parameter extraction, a `run` verdict, its
own entry point. Reasons to wait:

1. It opens a new correctness surface. A mis-extracted parameter runs the skill on the wrong
   input and returns a confident wrong answer, with nothing to catch it — the output schema
   checks shape, not sense. A project whose identity is "nothing unproven lands" should not
   ship that path without a gate.
2. It is a cost optimisation, not a capability gain. The agent already extracts parameters;
   tier 1 makes that one call instead of a loop. Worth having, not urgent.
3. Scope. The PR is already 51 files / +5971 lines.

**Sequence:** grade-aware `how_to_reuse` now → measure how much of the agent loop it removes
→ then decide whether tier 1 still earns its complexity. It may turn out that an agent told
"just run it" is already close enough to tier 1 that the dispatcher is redundant.

#### Correction — `executable` alone is not enough to say "run it"

`grade` answers *can it run*, not *will running it answer this task*. An `executable` skill
can still be wrong for the task in hand: the task may need a parameter the skill doesn't take,
or a field it doesn't return. Branching on grade alone would tell the agent to run a skill
that produces a confident, well-shaped, irrelevant answer — the same failure mode that made us
defer tier 1.

Two independent facts are needed:

| | question | where it comes from |
|---|---|---|
| **can it execute** | is this skill `executable`? | `meta.json` grade — a fact, already recorded |
| **does it fit** | do this task's inputs fall inside the skill's parameters? | the decide call — a *judgement*, not a fact |

And the fit half is only ever a judgement: `verdict: use` is the agent's stated intent, not a
verified match (the earlier audit found `use` returned for skills whose source barely overlapped
what was needed).

So the branch is three-way, and the "run" branch has to be phrased as an attempt with a
fallback, never as a command:

- **executable + judged in-range** → *"this one can be executed as-is — try
  `python <path>/skill.py taskspec.json` with these params first; if the answer doesn't
  actually address the task, fall back to adapting the source."*
- **executable + out of range** → *"it runs, but not for this task — take the source and
  adapt it."*
- **reference / unverified** → *"read it as a prior; it isn't trusted to run."*

That keeps the win (an in-range executable skill costs the agent a couple of steps instead of
a rewrite) without pretending the fit judgement is verified. It also means the "check the
answer actually answers the task" instruction has to survive into the prompt — the schema
checks shape, and shape is exactly what a wrong-but-executable skill will get right.

#### Router, or let the agent decide?

They solve different problems, and the difference is *who is already running*:

| | agent decides | router decides |
|---|---|---|
| **when it helps** | you are already inside an agent solve | you have a task and no agent yet |
| **what it saves** | the agent's work *within* a solve — a couple of steps instead of rewriting the skill | the entire agent loop — you never start one |
| **can it check itself** | yes: it holds the source, can run it, look at the page, and notice the answer doesn't fit | no: it commits to an answer with nothing downstream to catch a bad match |
| **cost of being wrong** | the agent keeps solving — a fallback it takes anyway | a confident, well-shaped, wrong answer returned to the caller |

**Default should be: the agent decides.** It is already there, it has the skill's source and
the live page, and its failure mode is benign — if the skill doesn't fit, it goes on solving.
All it is missing is information, and that is the cheap defect fix above (grade + the honest
three-way phrasing). Nothing new to build.

**A router earns its place in exactly one case: batch.** Many tasks of a family you already
have a skill for, where paying an agent loop *per task* is the entire cost. There, routing to
a skill and executing it directly is the whole point of having built the skill. For a single
ad-hoc task the router saves little — you'd have run one agent anyway — and it takes on the
risk the agent would have absorbed.

If a router is built, it should **escalate rather than guess**: run directly only when the
skill is `executable` and the fit is unambiguous, and hand anything else to the agent. The
asymmetry matters — escalating costs an agent loop you were willing to pay anyway; guessing
wrong costs a wrong answer nobody checks.

---

### 8. Retrieval belongs outside the agent loop — status: **open**

**Problem.** `_HINT` (`prompt.py:11-22`) injects a *command*, not an answer, so the lookup runs
*inside* the step loop. Every solve opens with roughly three steps before the browser is
touched at all: run `skill_use`, `cat source_path`, write `skill_decision.json`. Three model
calls, two large observations, and the worst case is the common one — when the verdict is
`skip`, the agent has paid all of it to learn the library cannot help.

**Why it is avoidable.** Every input to that lookup — the task text and the library path — is
known *before the agent starts*. Nothing in it depends on anything the loop discovers.

**Why it is cheap to fix.** The out-of-loop position already exists and already runs Python:
`solve_with_library.sh:11` builds the prompt in a `python -c` *before* `exec`, and `build.py:73`
does the same. And `skill_use.recommend(task, library_root)` is a plain importable function that
already returns `{verdict, skill_id, source_path, how_to_reuse, ...}`. So `with_skill_hint` can
call it directly, at the same call site, with the same signature:

- `skip` → return the prompt unchanged. No hint, no tokens, no steps.
- `use` / `adapt` → inject the verdict, the grade, and the source inline, so step 1 is real work.

**Trade-offs, honestly:**

- *Does retrieval get worse without the loop's context?* No — today's hint bakes in the very
  same launch-time task string (`--task {task_q}`). Same input, so no regression.
- *Bigger prompt when a skill is found?* The agent was going to `cat` that source anyway. Same
  tokens, one fewer round trip.
- *The agent loses the option to re-query mid-solve?* The hint already says "query it ONCE".
- *`skill_decision.json`* gets written by the launcher instead of the agent — more reliable
  for measurement, since agents forget.
- *Real new risk:* `decide` is an LLM call, so it now sits between launch and the agent. It
  needs a timeout and must **fail open** — on error, fall back to injecting no hint, never
  block the solve.

**Leaning.** Do it. It is confined to `prompt.py`, it removes a per-solve tax that is pure
waste on `skip`, and it composes with item 7: the grade-aware phrasing is computed once,
outside, where the ledger is readable — rather than being re-derived by the agent every run.
