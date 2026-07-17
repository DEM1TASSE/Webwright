# Quickstart — the complete tutorial

[← back to the module README](../../src/webwright/skill_factory/README.md)

Four sections, in the order you'd meet them:

1. **[Run the checked-in skill](#1-run-the-checked-in-skill)** — no model, no key, ~40 s.
2. **[Reuse it with the agent](#2-reuse-the-skill-with-the-agent)** — `ask` / `solve`, needs a key.
3. **[Watch the library get built](#3-watch-the-library-get-built-from-nothing)** — the Google
   Flights example, from nothing, ~40 min.
4. **[Do it for your own task](#4-do-it-for-your-own-task)** — `init` → fill → `build`, or
   `learn` if you already have runs. **This is the part that's yours.**

---

## 1. Run the checked-in skill

Task: *earliest nonstop flight* on Google Flights (the site from Webwright's own README)

```bash
cd src/webwright/skill_factory/examples
./quickstart.sh                            # SEA->DEN, date=today+30, ~40 s, no model, no API key
#   == ... earliest nonstop SEA->DEN on 2026-08-16 ...      <- it tells you the date it picked
#   -> answer shape: [flight number, airline, departure time]
./quickstart.sh demo LAX ORD 2026-09-01    # your own route (codes + YYYY-MM-DD)
```

The output contract is a three-item list: [flight number, airline, departure time]. The values depend on the current flight schedule.

With no arguments, the script searches for a SEA-to-DEN flight 30 days from the day it is run, so the date changes daily. You can compare the result with your own Google Flights search.

The script also prints all ten fixed execution steps and the location of the saved screenshots. No model selects these steps; they are fully encoded in the skill.

Each run directory contains the complete trajectory, including skill_log.txt and one screenshot per step, so you can check it by yourself. By default, each run uses a fresh temporary directory. Set QUICKSTART_WORKDIR=./run1 to save the output somewhere persistent.

## 2. Reuse the skill with the agent

```bash
export OPENAI_API_KEY=...
./quickstart.sh ask      # ~10 s — one LLM call: "can the library help here?" -> use/adapt/skip
./quickstart.sh solve    # ~5 min — a full agent solve of SEA->DEN, reusing the skill
```

`demo` (above) runs the skill standalone, no agent in sight.

`ask` is the agent deciding whether
to use a skill at all, and which one; it only **retrieves**, one round trip printing the JSON the
agent is handed (`verdict / skill_id / source_path / how_to_reuse`), which is the integration
surface.

`solve` is the agent actually doing the task with it.

## 3. Watch the library get built from nothing

The spec that produced the checked-in library ships with it. `--dry-run` prints the plan and
spends nothing:

```bash
cd src/webwright/skill_factory/examples
python -m webwright.skill_factory build flights.skill.yaml --library ./library --jobs 3 --dry-run
```

<details>
<summary><b>The same loop by hand, without the wrapper</b> — what <code>build</code> is doing for you</summary>

<br>

```bash
# custom / OpenAI-compatible gateway? TWO knobs, both needed:
#  1. env vars for learn / skill_use (or reuse is silently off). The endpoint is the
#     FULL request URL — ".../api" alone fails, ".../api/responses" works:
export OPENAI_ENDPOINT=https://your-gateway/api/responses   OPENAI_MODEL=your-model
#  2. the AGENT's model in the solve steps reads its yaml, NOT these env vars — copy
#     examples/model_gateway.example.yaml, fill in your endpoint/model, and use it
#     below in place of `-c model_openai.yaml` (quickstart.sh: export MODEL_CFG=...).
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

**What each way of running it actually costs** — task: earliest nonstop flight SEA→DEN on
2026-08-15, a route the skill never trained on, answered three ways on this machine:

|            | from scratch<br><sub>no library</sub> | the agent, with the library | the skill, standalone |
|------------|--------------|------------------|----------------------|
| steps      | 50           | **11**           | **10** (fixed)       |
| wall clock | 23.5 min     | **~4 min**       | **~40 s**            |
| LLM calls  | 55           | **12**           | **0**                |
| answer     | `WN 4697, Southwest, 6:50 AM` | same | same |

For reference, the three solves that *built* the skill took 25 / 40 / 59 steps and 11 / 26 / 32
minutes — same task type, three routes. That spread is the point: from-scratch cost is
high-variance because the agent re-derives the strategy every time, and the skill pins it to a
fixed 10.

How to read the middle column. The agent asked the library, got `use`, and stopped exploring:
50 steps to 11. That gap is a property of *this* task, not a promise. Google Flights is fiddly
enough that the agent flails without help; on a site the model already drives from memory, the
gap narrows or inverts, because querying and reading a skill isn't free. The honest general
version: **step savings scale with how much the agent doesn't already know.**

The last column doesn't depend on any of that. **Every run after the library exists uses no model
at all** — a schedule watcher in cron pays the agent exploration once, then ~40 s forever.

This loop, already run and checked in: `examples/learned_library/` (provenance in
`examples/README.md`).

---

## 4. Do it for your own task

You can run this loop on your own task. Two ways in, depending on what you already have.

### 4.1 — You have trajectories: `learn`

If you've been using Webwright anyway, the runs are already on disk: hand them straight to
`learn`, no spec to write.

```bash
python -m webwright.skill_factory learn outputs/ --library ./library
```

That's the day-to-day path.

### 4.2 — You have a task, but no runs yet: `init` + `build`

Describe it; `init` drafts the spec and leaves the values for you.

```bash
python -m webwright.skill_factory init "the earliest nonstop flight from A to B on a given date"
```

`init` makes one model call and writes `skill.yaml` — this is its real output, verbatim:

```yaml
# Draft skill spec — fill the ____ values (your ground truth), then: build skill.yaml
# The {holes} in `task` are the parameters; each is a column below.

task: Find the earliest nonstop flight from {origin_airport} to {destination_airport} on {travel_date} and return the departure time, arrival time, airline, and flight number.
start_url: https://www.google.com/travel/flights    # guessed — check it opens the right page

instances:            # give a few real instances (3+ makes a verifiable skill)
  - {origin_airport: "____", destination_airport: "____", travel_date: "____"}
  - {origin_airport: "____", destination_airport: "____", travel_date: "____"}
  - {origin_airport: "____", destination_airport: "____", travel_date: "____"}

build:                # optional policy — CLI flags override these
  # this answer should hold still (published flight schedules for a given future date typically remain the same tomorrow), so replay demands it back exactly
  verify: strict     # strict (reproduce answers) | shape (drifting data) | off
  draws: 2            # independent distillation attempts — a draw can come out brittle
  verify_rounds: 2    # repair rounds within one attempt
  on_fail: reject     # reject = executable or nothing | reference = keep it as a prior
  chunk: 25
```

**It proposes the structure and leaves the values blank on purpose.** The template, the site and
the verify mode are guesses you can overrule; the values are your ground truth, and a value the
model invented would quietly train the skill on an answer nobody checked. Fill the `____`s, look
at the guessed `start_url`, then:

```bash
python -m webwright.skill_factory build skill.yaml --library ./library --jobs 3   # 3 at once
```

`build` = **solve × N + learn**. It fills the template with each instance, prints the tasks it's
about to solve and asks before spending agent time (`--dry-run` shows the plan and stops,
`--yes` skips the prompt), solves them, and hands the batch to `learn`. **An instance that
already produced an answer is never re-solved** — if a run dies halfway, re-running `build` only
pays for what's missing. Solves are slow (10-30 min each) and independent, so `--jobs N` runs N at a time. `build` still
blocks until the last one finishes, so if your shell or tooling enforces command timeouts, run it
in the background. The [reference](reference.md#all-parameters) has the tuning and the rate-limit
caveat.

### Vary the parameters, not just the count

Distillation lifts a parameter from the differences it **observes**, so a value identical in
every instance may get baked in. Two instances that vary everything you care about beat five that
share a date.

### Choosing a task that can be verified

Four questions, learned the hard way. The example passes all four; "the cheapest X" fails three:

1. **Does the page state the answer?** — or must you infer and compare it yourself? A skill can
   anchor on what the site declares (a Cheapest tab's own label, a sort control); it can't
   anchor on your judgement.
2. **Does the answer hold still?** — if it drifts on its own (prices, stock, rankings), `strict`
   will reject a working skill for reporting today's truth. Use `shape`: it still catches a
   **broken** skill (empty or misshapen output), but never a **wrong** one — for that you need
   `--golds`. `init` guesses this for you and writes the reason into the spec.
3. **Can each field be extracted reliably?** — truth being well-defined isn't enough. A flight
   number is stated plainly and *still* sits glued to the aircraft type (`Airbus A321neo` `UA 729`)
   next to look-alike tokens, so it's the field distillation gets wrong; the airline and the
   departure time never were.
4. **Is the value the site declares the value you actually want?** — the subtle one. Sorting
   Amazon by price ascending is the *right method* and faithfully returns `$0.00` placeholder
   listings. The skill is correct and the answer is useless. A declarative anchor tells you
   *where to read*; it can't tell you you're reading the right thing.

### When a skill gets rejected

Rejection is the gate working — nothing unproven lands, and the runs stay retryable (they're
kept out of `library/.learned.json`, so re-running `learn` retries without re-solving). Two kinds:

| what you see | what it means | what to do |
|---|---|---|
| the diff is only in a value that moves (`$0.01` → `$5.99`), other instances reproduced exactly | the **verify mode** is wrong for this task, the skill is fine | `--verify shape` |
| a crash (`Could not choose ...`), or an answer off in the wrong place | the distilled skill really is broken | **re-run `learn`** — distillation is stochastic, a fresh draw often lands; the failure prints the crash, and the last candidate is kept at `library/.rejected_<id>.py` for a post-mortem |

Distillation is one LLM call — a re-draw costs a rounding error next to the solves you already
paid for. `--verify-rounds N` bounds how many repair rounds one draw gets before it gives up.

---

**Where this fits:**
- *recurring personal queries* — releases, commit counts, price checks: pay the exploration
  once, every repeat is cheap (or free — run the skill standalone from cron, no model);
- *same-template batch jobs* — QA flows, report pulls: solve 3, learn, run the rest on skills;
- *a team library* — commit `./library` to your repo; everyone's agent reuses it.

**Need every field under your control** — explicit manifests, benchmark-grade gold gates?
That's [manual mode](manual.md); you don't need it to get started.

