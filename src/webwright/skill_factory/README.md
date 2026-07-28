
# Web Skill Factory: Evolving Reusable, Verified, Code-Native Skills for Web Agents

**Most agent skills are context the model refers to. Ours are programs.**
 
Every task Webwright solves leaves a working script behind. The Skill Factory turns those
scripts into a growing library of **reusable, verified, parameterized skills**: code you can
run without a model and compose into the next task instead of re-exploring the site.

## 🎥 Demo



https://github.com/user-attachments/assets/a6cb7d8e-2411-4d14-b85e-4255ccb1ae81




## ✨ Highlights
 
- 🏃 **Runs standalone, no model.** A learned skill is just code. It re-executes in ~40 s with zero tokens, so you can schedule it to run every day, instead of having a model re-read a note and redo the work every time.
- 🛠️ **Has a real software-engineering surface.** Because skills are code, they inherit code's tools and properties for free: inheritance, polymorphism, encapsulation, tests, versioning, and history. A skill is executable and verifiable, not prose the model has to interpret.
- ✅ **Verified twice before it lands.** First an input gate: a solve only becomes material if it got the task right, so a wrong answer never feeds a skill. Then the distilled skill must replay its own answers standalone, with no model, so a broken skill can't slip in and poison the library.
- 🌱 **Gets stronger the more you use it.** New solves widen a skill in place, self-evolving as you go. Regression-replay keeps old coverage from breaking, so a skill that's already been verified is never damaged by a later change.


## 🗺️ How it works

![components, the loop, and what a skill is](../../../assets/skill_factory_pipeline.png)

The system adds two integration points to WebWright without changing the agent loop:

* **Reuse, resolved out of the agent loop:** before the agent starts, the library is checked for a skill that fits the task, and only the *result* is used — injected into the agent's prompt as a hint, or (via `route`) run directly with no agent at all. The agent never spends its own steps querying the library.
* **Library growth after solving:** the `skill_factory` CLI, through `init`, `build`, `learn`, and `update`.

The decision is `recommend`: given the task and the library, it retrieves candidates, judges fit, and returns a verdict — `run`, `adapt`, or `skip` — with the chosen skill, how to reuse it, and the filled parameters. It doesn't *do* anything; it only decides. It is not a command you call, and not a tool the agent invokes from inside its loop — it's the piece both the prompt-hint injection and `route` are built on.

`route` is the out-of-loop entry that acts on that decision. On `run` — an executable skill that covers the task and whose parameters all fill — it executes the skill directly, no model, and only falls back to the agent if that run fails or comes back the wrong shape. On `adapt` it hands the task to the agent with the skill as a prior; on `skip` the agent starts fresh. So `route` is just `recommend` plus carrying the verdict out: a match you can trust runs for free, and anything short of that still gets solved. It's one call path, not two stacked routers — you don't call `recommend` yourself.

After solving, the library grows from the runs you already have. Solves of the same task template are aligned: what is identical becomes the skeleton, and what differs is lifted into parameters, giving one parameterized program per template. The expensive part, driving the site itself, is factored into named primitives (log in, run a search, read the results table), so a later task on the same site can call them even when its final step differs.

Two gates decide what lands: before distillation, only correct solves become material; after it, the candidate must replay its own answers standalone, with no model. When a template already exists, its skill is widened in place, and every answer it previously reproduced is replayed alongside, so a later batch can't break what already worked.

<details>
<summary><b>How it compares to related work</b></summary>
<br>

|  | published `SKILL.md` | [SkillOpt](https://github.com/microsoft/SkillOpt) | [OpenCLI](https://github.com/jackwener/OpenCLI) | [OpenSpace](https://github.com/HKUDS/OpenSpace) | **Web Skill Factory (Ours)** |
|---|---|---|---|---|---|
| **what a skill is** | a document the model reads | a document the model reads | ready-made commands for website tasks, plus general tools for driving any page | a document (with optional helper files) the model reads and follows | **an executable program — no model to run it (the agent can still use it)** |
| **how one skill covers different inputs** | the model interprets the author's written guidance for each input | the model adapts the optimized document to each input | a person or agent anticipates the variation and declares explicit arguments | the agent interprets the document for each input; larger differences may lead to fixed or derived documents | **verified runs of the same task template are aligned; their observed differences may become explicit parameters in one executable skill** |
| **how it's verified** | no built-in verification requirement | a candidate replaces the current document only if it scores higher on a validation split | the author runs the command against the live site, checks its output against saved constraints (format, non-empty, row count), and compares the values with the live page | admission only checks a new skill is well-formed and doesn't regress the library; it then stays *untrusted* until real successful use promotes it to *trusted* (a failure it caused demotes it) | **the program must reproduce its recorded answers exactly to check consistency; supplying known answers additionally checks correctness** |
| **how the library evolves from runs** | it does not evolve automatically | scored runs are used to update a skill document — edits kept only when they raise the validation score | CLI commands don't generalize from repeated solves on their own — a person or agent adds and maintains them, and site knowledge builds up as they do | runs may fix an existing skill document, produce a derived document, or add a captured document | **a new task template adds an executable skill; a successful reuse leaves it unchanged; an adapted run is refined back in — newly observed differences may become parameters, and the skill can be repaired or made more robust** |

_Compared as of 2026-07-23, against SkillOpt @ 61735e3, OpenCLI 1.8.6, and OpenSpace @ 2c5cc40. These projects move quickly and this table may fall behind. If we've mischaracterized your project, please open an issue or PR — we'll fix it._

</details>

The Quick Start below demonstrates the complete workflow.

## 🚀 Quick Start

Set it up once. The module ships with Webwright, so clone the repository and install it locally:

```bash
git clone https://github.com/microsoft/Webwright.git
cd Webwright
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

Then configure a model. Step 1 does not require one, but every subsequent step does:

```bash
export OPENAI_API_KEY=...
```

<details>
<summary><b>Using a custom OpenAI-compatible gateway</b></summary>
<br>

Export two environment variables. That is the entire setup:

```bash
export OPENAI_ENDPOINT=https://your-gateway/api/responses   # Full request URL, not a base URL
export OPENAI_MODEL=your-model
```

`init`, `learn`, `build`, and `route` all respect these variables.

This also applies to the browser agent, even though its model configuration comes from YAML and cannot read environment variables directly. `build` and `route` translate the environment variables into the appropriate agent configuration, and `build` prints the final configuration it used.

You only need a custom YAML file when you want the browser agent to use a different model from the one used for skill distillation. Copy [`examples/model_gateway.example.yaml`](examples/model_gateway.example.yaml), set `model_name` and `openai_endpoint`, and pass it with `-c base.yaml -c $HOME/my_gateway.yaml` to `build` or `route`. Because `-c` replaces the default configuration files, make sure to include `base.yaml`.

</details>

### 1. Run a learned skill

Task: *what is the earliest nonstop flight from A to B on this date?*, on the
live Google Flights.

A learned skill is a plain CLI. Run it directly — no model, no API key, about 40 seconds:

```bash
python src/webwright/skill_factory/examples/learned_library/what_is_the_earliest_nonstop_flight_from_2c8dab1/skill.py \
    --origin-city SEA --origin-code SEA --destination-city DEN --destination-code DEN --date 2026-08-26
```

The skill takes all five parameters as `--flags` (for airport codes, city and code can be the same); it also accepts a positional `taskspec.json`, which is what replay and programmatic callers use. Change the codes and date for your own route.

It prints the ten fixed steps it executed and the location of the saved screenshots. The steps are encoded in the skill, not chosen by a model. The run directory (under `$WORKSPACE_DIR`) contains the full trajectory.

> **This skill was distilled on Linux, against Google Flights as it looked then, and that's all
> `strict` replay proved.** It's plain Playwright driving a live site it doesn't control, so a
> different OS or a page Google has since changed can break it — on macOS it fails at the airport
> field, for instance, because the field-clearing shortcut it learned (`Control+A`) is select-all
> only on Linux/Windows. That fragility is the point of the research, not a bug in your setup: a
> replay-verified skill reproduces its *training* run, which is not the same as generalizing.
>
> When the standalone run won't work, the agent still can. `route` (§2) carries the skill to the
> agent as a prior it reads and adapts around the difference; run it without `--start-url` first to
> just see the decision. Keep that solve and `learn` folds it back in, so the next standalone run
> has your platform covered too.

---

### 2. Bring the agent in

Now a task the skill *doesn't* quite fit — which is exactly when the agent comes into the loop. We ask for the nonstop with the **shortest flight duration**, while the checked-in skill finds the **earliest departure**. That's nearly the same job — one different filter over the same results table — so the skill is a strong prior, but it can't be run as-is. `route` sees that, decides `adapt`, and hands the task to the agent with the skill to adapt around the difference. One command decides and then acts. Needs an API key:

```bash
python -m webwright.skill_factory route \
    --task "What is the nonstop flight with the shortest flight duration from Seattle (SEA) to Denver (DEN) on 2026-08-26 (one-way)? Return the answer as a list: [flight_number, airline, duration]." \
    --library ./library \
    --start-url https://www.google.com/flights -c <your_model.yaml>
```

`route` searches the library, picks a skill, and decides `run` / `adapt` / `skip`, printing the decision (verdict, skill, why) before it acts. Then it carries the decision out: on `run` it executes the skill directly with no model; otherwise it launches the agent to adapt the skill, and a direct `run` that fails falls back to the agent too. Here the shortest-duration task can't run the earliest-departure skill as-is, so `route` returns `adapt`. Give it a task the skill fits and you'd see `run`, executed directly.

Drop `--start-url` to inspect only: `route` prints the decision (and still runs a directly-runnable skill), but doesn't launch the agent. That's the cheap way to see the choice before spending a solve.

**What that just saved.** Reusing the skill helps even when the agent has to adapt it — and it buys steadiness, not just speed. Five solves **with** the library (`route` → `adapt`) against five **without** it (empty library → the agent from scratch), same shortest-duration `SEA → DEN` task, `gpt-5.4`:

|                     | from scratch<br><sub>shortest-duration</sub> | with the library<br><sub>agent adapts the skill</sub> | skill standalone<br><sub>earliest nonstop departure</sub> |
|---------------------|:---:|:---:|:---:|
| steps — mean of 5   | 26.0 | **21.8** | **10**, fixed |
| steps — worst of 5  | 39   | **29**   | — |
| final attempts      | 5.8  | **4.6**  | — |
| correct             | 5/5  | 5/5      | ✓ |

Reuse lowers the mean (21.8 vs 26), the spread (std 6.6 vs 8.2), and the worst case (29 vs 39) — even the *unluckiest* run with the library beats the unluckiest without it, so this isn't a lucky draw. The skill hands the agent an already-debugged path instead of leaving it to wander and retry. (The `self_reflection` evidence gate is skill-independent noise that keeps the absolute step counts high; it hides how large the saving is, not its direction.)

The last column is the skill running standalone on its *own* task — the **earliest nonstop departure** from §1, not the shortest-duration one the agent solved. Different question, nearly identical work: one filter changed over the same results table. So it's a fair floor for the same machinery — once a skill fits your task exactly, every repeat runs in a fixed handful of steps with no model at all.

---

### 3. Build your own skill

Everything below requires an API key. The normal path is `init` → `build`: describe the task, review the draft, and let `build` solve a few instances and learn a skill from them. If you *already* have finished Webwright runs on disk, `learn` is the shortcut — skip to 3.2.

**3.1 — You have a task.** Describe it; `init` drafts a spec you review, then `build` solves the
instances and learns a verified skill.

```bash
python -m webwright.skill_factory init "the earliest nonstop flight from <origin> to <destination> on <date>"
```

```yaml
# skill.yaml — the {holes} are the parameters; each is a column below
task: Find the earliest nonstop flight from {origin_city} to {destination_city} on {travel_date} and return the departure time, arrival time, and flight number.
start_url: https://www.google.com/flights    # guessed — check it opens the right page

instances:            # PROPOSED — real, varied guesses to review, edit, add or delete
  - {origin_city: "Seattle", destination_city: "New York", travel_date: "2026-08-15"}
  - {origin_city: "Los Angeles", destination_city: "Chicago", travel_date: "2026-09-10"}
  - {origin_city: "San Francisco", destination_city: "Boston", travel_date: "2026-10-05"}

build:                # every key here is also a CLI flag; the flag wins
  # this answer holds still (a published schedule reads the same tomorrow), so replay demands
  # the same answer back — a drifting answer like a price would use verify: shape instead
  verify: strict
  draws: 2            # fresh attempts: bin the candidate, distil a new one from the same runs
  verify_rounds: 2    # repair rounds inside one attempt: feed it its failures, try again
  on_fail: reference  # reference = keep a readable prior if replay fails | reject = executable or nothing
  chunk: 25           # runs per grouping call
```

`init` proposes the task template, site, verification mode, and a few real, varied instance values to start from. Review them — replace any that are wrong, since a bad value quietly trains the skill on the wrong answer — then run `build`. (For an account-scoped task, where the values are private to your login, `init` leaves the rows blank rather than invent them.)

```bash
python -m webwright.skill_factory build skill.yaml --library ./library --jobs 3
#                                                       where it lands ↑    ↑ solve 3 at a time
#   on a gateway: nothing extra — build points the agent at your OPENAI_ENDPOINT / OPENAI_MODEL
#   and prints the config it used. Pass -c only to give the agent a *different* model.

# no spec of your own yet? the one behind the checked-in library is sitting next to you in
# examples/, and --dry-run only prints the plan — no key, no browser:
python -m webwright.skill_factory build flights.skill.yaml --library ./library --dry-run
```

`build` runs `solve` for each instance, then calls `learn`. It prints the planned tasks and asks before starting. `--dry-run` prints the plan and exits. An instance that already has an answer is not solved again. `--jobs N` sets the number of parallel solves and defaults to 1. The practical limit is the target site. Too many browsers from one IP may trigger throttling. Start with 3 to 5.

> For changing answers such as prices or rankings, shape verification can detect a broken skill but cannot verify that the answer is correct. Provide `--golds` or use a judge, as described in Limitations.

<details>
<summary><b>The same loop by hand, without the wrapper</b> — what <code>build</code> is doing for you</summary>

<br>

```bash
cd src/webwright/skill_factory    # commands below run from the module directory

# 1. SOLVE a few instances of the same task type (library is empty — these run from scratch)
TASK='What is the earliest nonstop flight from %s to %s on 2026-08-15 (one-way)? Return the answer as a list: [flight_number, airline, departure_time], e.g. ["AS 336", "Alaska", "6:00 AM"].'
while IFS='|' read -r FROM TO; do
  examples/solve_with_library.sh \
    "$(printf "$TASK" "$FROM" "$TO")" \
    https://www.google.com/flights "$PWD/library" -o outputs -c base.yaml -c model_openai.yaml
done <<'ROUTES'
Seattle (SEA)|New York (JFK)
San Francisco (SFO)|Boston (BOS)
Los Angeles (LAX)|Chicago (ORD)
ROUTES

# 2. LEARN: distill everything you've solved into skills — no manifest, no fields to fill.
#    --verify strict: the distilled skill must reproduce all three training answers standalone
#    before it lands (a schedule is stable, so this is a fair bar).
python -m webwright.skill_factory learn outputs/ --library ./library --verify strict --verify-rounds 3
# -> groups the 3 runs into ONE template and lifts FIVE parameters:
#    origin city/code, destination city/code, date
#    library/what_is_the_earliest_nonstop_flight_from_.../{skill.py, meta.json, replays.json}

# 3. USE the library: same wrapper, an UNSEEN route — the agent finds and reuses the skill
examples/solve_with_library.sh \
  "$(printf "$TASK" 'Seattle (SEA)' 'Denver (DEN)')" \
  https://www.google.com/flights "$PWD/library" -o outputs -c base.yaml -c model_openai.yaml
# outputs/<run>/skill_decision.json -> {"verdict": "use", "skill_id": "what_is_the_earliest_nonstop_..."}
```

</details>

**3.2 — You already have runs.** `learn` is the shortcut: it's exactly what `build` does after
solving, so it skips straight to distilling. Point it at a folder of finished Webwright runs.

```bash
python -m webwright.skill_factory learn outputs/ --library ./library
```

Never run Webwright, so you have nothing to try it on? Three real solves ship with the repo:

```bash
cd src/webwright/skill_factory/examples
python -m webwright.skill_factory learn trajectories --library ./library --verify off
```

~100 s: three runs → one template → five lifted parameters → one skill.

These trajectories use flights scheduled for August 15, 2026. We use `--verify off` to skip browser replay and keep the example stable if the schedule changes or the date passes. Before August 15, 2026, you can also try `--verify strict`. [The trajectory README](examples/trajectories/README.md) explains when the examples become stale.

A verified skill built from these trajectories is included in [`examples/learned_library/`](examples/learned_library/). It has `verified: true` and `grade: executable`, and is the skill used in step 1. Everything here was produced with **gpt-5.4**, which we recommend.

<details>

<summary><b>What to expect from skill distillation</b></summary>

<br>



Distillation is stochastic. On the same set of runs, about **40% of draws pass verification on the first attempt**, so `--draws` defaults to 2. Each draw creates a fresh candidate.



A rejection only costs another distillation, which is much cheaper than solving the tasks again. `build` keeps the trajectories in `build_outputs/`, so you can retry without rerunning them. Failed runs are not added to `library/.learned.json`, so `learn` will pick them up again. Once a skill lands — `executable` or `reference` — its runs are marked as learned and skipped on future builds.



If repeated draws fail, inspect the failure:



* **The skill crashes.** Try another draw. If it keeps failing, inspect `library/.rejected_<id>.py`, which contains the last candidate and its traceback.

* **The skill returns a valid answer that differs from the recorded answer.** The recorded answer may be wrong. Without `--golds`, the original agent answer was not independently checked. Remove that run or provide the correct answer for its `task_id`:



  ```bash
  python -m webwright.skill_factory learn build_outputs/ --library ./library \
    --golds '{"<task_id>": "<right answer>"}'
  ```



  This verifies that run against the supplied answer while leaving the others on `self_verify`.

* **Only a changing value differs**, such as a price or count. Strict replay does not fit the task. Use `--verify shape`.



By default (`on_fail: reference`), a candidate that never passes replay still lands, kept with `grade: reference`: the agent can reuse its selectors, URLs, and parameter structure, but it is not trusted to run independently. Strict replay is slow, a little brittle, and a bit of a lottery, so the default leaves you with a readable prior the agent can adapt rather than nothing. Pass `--on-fail reject` for the stricter executable-or-nothing bar: a failed candidate lands nothing and its runs stay retryable. Landing a `reference` skill is a one-way door for that template: the skill now exists and its runs are ledgered, so a later `learn` skips those runs and won't replace it. To go again for an `executable` one, delete the skill *and* its runs' entries from `library/.learned.json` — dropping the skill alone leaves the runs marked learned, and `learn` will find nothing to do.



</details>

## 📊 Results

**Setting.** WebArena, 10 retrieve-type task templates across 3 self-hosted sites
(shopping-admin, gitlab, map). Each template contributes 3 train solves that build the library
(gated on ground-truth answers) and 2 held-out instances that measure reuse on unseen instances
of the same template. Every task is solved both with the library and from scratch. Model:
gpt-5.4. 100 runs in total.

|                         | WITH library | from scratch |    Δ    |
|-------------------------|--------------|--------------|---------|
| held-out accuracy (20)  | **70%**      | 55%          | **+15 pp** |
| held-out avg steps      | **14.7**     | 17.1         | −2.4    |
| train accuracy (30)     | **86.7%**    | 76.7%        | +10 pp  |
| train avg steps         | **13.7**     | 15.9         | −2.2    |

- **Reuse helps most when solving from scratch is expensive.** Of 20 held-out tasks, 4 were
  rescued (they failed from scratch and the library solved them) and 6 more solved in fewer
  steps. The +15pp is measured on instances that never took part in building the library; the
  same direction holds on training instances (86% vs 76%).
- **Biggest single win:** a task that took 33 steps from scratch ran in 10 with the library.
- **Wrong solves stay out.** 7 of 30 train solves failed the ground-truth gate and never
  entered the library.
- **Retrieval stayed reliable as the library grew** to 10 skills: all 20 held-out solves
  retrieved their own template's skill, including two near-duplicate gitlab commit skills.

**How to read it.** In the agent-in-loop path (a `reference` skill the agent reads and reuses,
which is what the eval runs), step savings scale with how much the agent doesn't already know:
on a familiar site the cost of querying the library and reading the skill can outweigh what it
saves, so reuse pays off most on the hard tasks. From-scratch cost is also high-variance, and a
skill pins the strategy down.

An `executable` skill skips that path entirely: it runs standalone, with no agent and no model
in the loop, in a fixed handful of steps, so every repeat after the first is essentially free.
(Results on this mode coming soon.)

## 🚧 Limitations & Roadmap

Here are some known rough edges, and directions we might take them.

- **A skill can't outrun the agent that made it.** Everything is distilled from solves, so if the
  agent never figured out a good way to do something, there's nothing to distill. Pooling a bunch
  of failed attempts won't invent a strategy that was never there. The factory makes reuse cheap;
  it doesn't make hard tasks solvable.

- **The agent reaches for skills too eagerly.** Right now `decide` only asks "is there a relevant
  skill?", not "is using it actually worth it?" On WebArena it said `use` 49 times and `skip` not
  once, even on tasks that would've been quicker from scratch. It should weigh the two, and skip
  when starting fresh is the cheaper bet.

- **Reuse today is copy-and-edit, not a clean import.** The agent reuses a skill by reading the
  source and editing a copy, which is why `use` and `adapt` blur together in practice, and even a
  `use` can quietly rewrite half the code. A proper callable interface, where you import a skill
  and just pass it parameters, would make reuse a lot cleaner.

- **Verification is only as reliable as the reference answer it checks against.** On real websites, where no gold label is available, the LLM may misinterpret the task or produce an incorrect reference answer, and self-verification may fail to detect that error. For dynamic answers such as prices or rankings, verification often falls back to checking only the output format or structure. This can catch a skill that is broken or fails to execute, but not one that executes successfully and returns the wrong result. Achieving true correctness in these settings requires a stronger, independent judge like WebJudge.

- **A direct run can be right-shaped but wrong.** When `route` runs a skill directly, it only catches
  *observable* failures — a crash, a timeout, empty output, the wrong shape. It can't catch a run that
  returns a well-shaped but wrong answer, which usually traces back to a slot filled with another
  plausible value (the date `8/15` filled as `8/5`, say). With no gold answer there's nothing
  machine-checkable to flag it, so there's no after-the-fact fallback for this case. The only guard is
  the *before*-run fit judgment — does the skill's template actually hold the task, is the filled value
  appropriate — not an after-run check. How well that pre-run judgment holds up end-to-end isn't
  measured yet; that needs many independently-runnable skills, and the library has only 2 executable
  ones today. Until then the conservative move is to keep direct-run off by default, or turn it on only
  for high-confidence matches.

- **Where the fallback lives.** The fallback isn't in `recommend` — that stays a pure decision. It
  sits one level up, in the orchestrator (`route`): a direct `run` that fails is downgraded in place to
  an `adapt`, handing the skill's source to the agent, so it reuses the existing agent path instead of
  a second mechanism.

- **Distillation is stochastic.** A given attempt may produce a fragile skill that fails even its own replay. The gate filters out these failures, and rerunning distillation a few times usually succeeds. However, each retry consumes additional tokens, so improving the reliability of executable skill generation, ideally succeeding on the first attempt, remains an important direction to explore.

- **The library needs upkeep, like any package registry.** After a skill lands, a site can shift
  under it with nothing re-checking, so it can quietly go stale and keep returning wrong answers.
  Stale skills never retire, and near-duplicate ones never get merged.
  Natural next steps include automated health checks, a retirement policy, and de-duplication.

## 📚 Documentation

| doc | what's in it |
|---|---|
| [docs/skill_factory/manual.md](../../../docs/skill_factory/manual.md) | manual mode: you declare the template, params, and admission yourself. Use it for benchmarks (pipe your evaluator's verdict in as the gate), logged-in sites, or cases where an LLM shouldn't be guessing your template |
| [docs/skill_factory/reference.md](../../../docs/skill_factory/reference.md) | verification & grades, every flag and env var, component map, backend |
| [examples/README.md](examples/README.md) | the checked-in skill and the example inputs |

## 📝 Citation

```bibtex
@misc{webskillfactory,
  title  = {Web Skill Factory: Evolving Reusable, Verified, Code-Native Skills for Web Agents},
  author = {Wang, Demi Ruohan and Lu, Yadong},
  year   = {2026},
  note   = {Built on WebWright},
  url    = {TBD}
}
```
