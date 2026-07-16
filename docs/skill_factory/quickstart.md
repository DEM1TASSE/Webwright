# Quickstart — the complete tutorial

[← back to the module README](../../src/webwright/skill_factory/README.md)

Four sections, in the order you'd meet them:

1. **[Run the checked-in skill](#1-run-the-checked-in-skill)** — no model, no key, ~40 s.
2. **[Reuse it with the agent](#2-reuse-the-skill-with-the-agent)** — `ask` / `solve`, needs a key.
3. **[Watch the library get built](#3-watch-the-library-get-built-from-nothing)** — the Google
   Flights example, from nothing, ~40 min.
4. **[Do it for your own task](#4-do-it-for-your-own-task)** — `init` → fill → `build`, or
   `learn` if you already have runs. **This is the part that's yours.**

Solves are long (10-30 min each). If your shell or tooling enforces command timeouts, run them
in the background — `--jobs` shortens the wall clock but the command still blocks until the last
one finishes.

---

## 1. Run the checked-in skill

```bash
cd src/webwright/skill_factory/examples
./quickstart.sh                            # SEA->DEN, ~40 s, no model, no API key
./quickstart.sh demo LAX ORD 2026-09-01    # your own route (codes + YYYY-MM-DD)
```

It prints the ten fixed steps it took — no model chose them, they're the skill's code — and
where it saved its screenshots, so "this is a program, not a model improvising" is something
you can check rather than take on faith.

The example is *earliest nonstop flight* on Google Flights (the site from Webwright's own
README). That task was chosen carefully, and the reason matters more than the example:
a flight **schedule** is a fact the page states plainly, it doesn't move on its own, and it
reads the same on your machine as on ours. That's what lets the skill be replay-verified
(`--verify strict`) and reused standalone with a straight face. The **fare** on the same page
would fail all three. See [choosing a task](#choosing-a-task-that-can-be-verified).

## 2. Reuse the skill with the agent

The library already has the skill; this is the agent using it. Same route as step 1, so the
numbers are comparable.

```bash
export OPENAI_API_KEY=...
./quickstart.sh ask      # ~10 s — one LLM call: "can the library help here?" -> use/adapt/skip
./quickstart.sh solve    # ~5 min — a full agent solve of SEA->DEN, reusing the skill
```

`demo` (above) runs the skill itself. `ask` only **retrieves** — one round trip printing the JSON
the agent is handed (`verdict / skill_id / source_path / how_to_reuse`), which is the integration
surface, at a tenth of a solve's cost. `solve` is the agent actually doing the task with it.

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

The library is also usable **without the agent** — this is the whole point of code skills:

```bash
# ask it whether it can help a task (the same call the agent makes — one LLM round trip)
python -m webwright.tools.skill_use \
  --task "earliest nonstop flight from Seattle (SEA) to Denver (DEN) on 2026-08-15" \
  --library ./library

# or run the learned skill directly — no model in the loop, ~40 seconds
SKILL=$(ls "$PWD"/library/what_is_the_earliest_nonstop_flight_*/skill.py)
cd "$(mktemp -d)"    # scratch dir: the skill writes its artifacts to the cwd
cat > taskspec.json <<'EOF'
{"params": {"origin_city": "Seattle", "origin_code": "SEA", "destination_city": "Denver",
            "destination_code": "DEN", "date": "2026-08-15"},
 "output_schema": {"type": "array", "items": {"type": "string"}}}
EOF
python "$SKILL" taskspec.json
# -> {"retrieved_data": ["UA 2601", "United", "5:00 AM"]}   (schedule may shift by season)
```

**What each way of running it actually costs** — one question, SEA→DEN, a route the skill never
trained on, answered three ways on this machine:

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
50 steps to 11. That gap is a property of *this* task, not a promise — Google Flights is fiddly
enough that the agent flails without help, and on a site the model drives from memory the gap
narrows or inverts (querying and reading a skill isn't free). The honest general version:
**step savings scale with how much the agent doesn't already know.**

The last column doesn't depend on any of that. **Every run after the library exists uses no model
at all** — a schedule watcher in cron pays the agent exploration once, then ~40 s forever.

**Verification, honestly:** because a schedule is a fixed, client-independent fact, this
family earns `--verify strict` — the distilled skill had to reproduce all three training
answers standalone before it landed (`meta.json`: `verified: true, grade: executable`). And
the standalone answer above, `["UA 2601", "United", "5:00 AM"]`, is byte-identical to what an
**independent** model-free probe reads off the page (`experiments/tools/earliest_nonstop_probe.py`
in the research repo) — two different code paths, one answer, so the check is real and not
self-confirming. This is the property the task selection buys you: pick a task whose truth the
page *states* and that doesn't drift by client, and admission becomes real verification without
hand-written golds. (For families whose answer genuinely changes between solve and replay —
live prices, inventory — use `--verify shape` instead, and pass `--golds` when you have them.)

Exactly this loop, already run and checked in: `examples/learned_library/` (provenance in
`examples/README.md`).

---

## 4. Do it for your own task

The example above is ours. This is the part that's yours.

```bash
# a task you keep repeating -> draft a spec
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
  # this answer should hold still (published flight schedules for a given future date typically
  # remain the same tomorrow), so replay demands it back exactly
  verify: strict     # strict (reproduce answers) | shape (drifting data) | off
  verify_rounds: 2
  on_fail: reject     # reject | reference
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
pays for what's missing. Solves are slow and independent, so `--jobs N` runs N at a time; the
[reference](reference.md#all-parameters) has the tuning and the rate-limit caveat.

#### When the answer moves on its own

`init` also judges whether your answer **drifts**, and picks the verify mode to match. Ask it for
something live and it says so in the spec it writes:

```bash
python -m webwright.skill_factory init "the latest release version of a GitHub repo, for any repo"
```
```yaml
build:
  # this answer drifts (new releases can be published), so replay only checks the shape —
  # strict would reject a working skill for reporting today's truth
  verify: shape
```

That's the difference `strict` can't paper over: a flight schedule for a fixed future date reads
the same tomorrow, so demanding the recorded answer back is fair. A release version doesn't —
`strict` would reject a perfectly good skill for correctly reporting a newer one. `shape` still
catches a **broken** skill (empty or misshapen output); it just can't catch a **wrong** one. For
that you need `--golds`.

### Already have runs? Skip the solving

If you've been using Webwright anyway, the trajectories are already on disk — hand them straight
to `learn`, no spec to write:

```bash
python -m webwright.skill_factory learn outputs/ --library ./library
```

That's the day-to-day path. The rest of this section is for a task you *haven't* solved yet.

### Vary the parameters, not just the count

Distillation lifts a parameter from the differences it **observes**, so a value that's identical
in every instance has no evidence behind it and may get baked in. Two instances that vary
everything you care about beat five that share a date.

### Choosing a task that can be verified

Four questions, learned the hard way. The example passes all four; "the cheapest X" fails three:

1. **Does the page state the answer?** — or must you infer and compare it yourself? A skill can
   anchor on what the site declares (a Cheapest tab's own label, a sort control); it can't
   anchor on your judgement.
2. **Does the answer hold still?** — if it drifts on its own (prices, stock, rankings), `strict`
   will reject a working skill for reporting today's truth. Use `shape`. `init` now guesses this
   for you and writes the reason in the spec.
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

