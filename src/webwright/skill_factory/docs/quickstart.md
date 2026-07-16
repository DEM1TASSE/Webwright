# Quickstart — the complete tutorial

[← back to the module README](../README.md)

Three ways in, in the order you'd meet them:

1. **[Run the checked-in skill](#1-run-the-checked-in-skill)** — no model, no key, ~40 s.
2. **[Watch the loop build it](#2-watch-the-loop-build-that-skill)** — the Google Flights
   example, end to end, ~40 min.
3. **[Do it for your own task](#3-do-it-for-your-own-task)** — `init` → fill → `build`, or
   `learn` if you already have runs. **This is the part that's yours.**

Solves are long (10-30 min each) — if your shell enforces command timeouts, run them in the
background or pass `--jobs`.

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

## 2. Watch the loop build that skill

```bash
export OPENAI_API_KEY=...
./quickstart.sh full     # 3 solves -> learn -> reuse on an unseen route (~40 min)
./quickstart.sh ask      # or: ask the library about a task it has never seen
./quickstart.sh solve    # or: watch the agent reuse the checked-in skill
```

What `full` does, spelled out:

```bash
export OPENAI_API_KEY=...
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

The library is also usable **without the agent** — this is the whole point of code skills:

```bash
# ask it whether it can help a task (the same call the agent makes — one LLM round trip)
python -m webwright.tools.skill_use \
  --task "earliest nonstop flight from Portland (PDX) to Austin (AUS) on 2026-09-01" \
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

**What each way of running it actually costs** — measured on this machine:

|             | from scratch (3 training routes) | the skill, standalone (SEA→DEN) |
|-------------|----------------------------------|---------------------------------|
| steps       | 25 / 40 / 59                     | **10** (fixed)                  |
| wall time   | 10.8 / 25.7 / 32.0 min           | **~40 s**                       |
| LLM calls   | 29 / 45 / 65                     | **0**                           |

How to read it: from-scratch cost is high-variance — the *same* task type took 25, 40 and 59
steps on three routes, because the agent re-derives the strategy each time (apply the nonstop
filter, sort by departure, expand the earliest row for its flight number). The learned skill
pins that strategy down to a fixed 10 steps, and the last column is the structural win:
**every run after the library exists uses no model at all** — a schedule watcher in cron pays
the agent exploration once, then ~40 s forever.

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

## 3. Do it for your own task

The example above is ours. This is the part that's yours.

```bash
# a task you keep repeating -> draft a spec
python -m webwright.skill_factory init "the cheapest <product> on Amazon, for any product"
```

`init` makes one model call and writes `skill.yaml`:

```yaml
task: Find the cheapest {product} on Amazon and return its brand and price.
start_url: https://www.amazon.com/    # guessed — check it opens the right page

instances:            # give a few real instances (3+ makes a verifiable skill)
  - {product: "____"}
  - {product: "____"}
  - {product: "____"}

build:
  # this answer drifts (prices/stock/rankings change on their own), so replay only
  # checks the shape — strict would reject a working skill when the value moved
  verify: shape
  verify_rounds: 2
  on_fail: reject
  chunk: 25
```

**It proposes the structure and leaves the values blank on purpose.** The template, the site and
the verify mode are guesses you can overrule; the values are your ground truth, and a value the
model invented would quietly train the skill on an answer nobody checked. Fill the `____`s, look
at the guessed `start_url`, then:

```bash
python -m webwright.skill_factory build skill.yaml --library ./library --jobs 3
```

`build` = **solve × N + learn**. It fills the template with each instance, prints the tasks it's
about to solve and asks before spending agent time (`--dry-run` shows the plan and stops,
`--yes` skips the prompt), solves them (`--jobs N` in parallel, progress every 30 s), and hands
the batch to `learn`. **An instance that already produced an answer is never re-solved** — if a
run dies halfway, re-running `build` only pays for what's missing.

Already have webwright runs lying around? Skip straight to the second half:

```bash
python -m webwright.skill_factory learn outputs/ --library ./library
```

### Vary the parameters, not just the count

Distillation lifts a parameter from the **differences it observes**. A value that's identical in
every instance has no evidence behind it and may get baked in. So two instances that vary
everything you care about beat five that share a date:

```yaml
instances:   # origin, destination AND date all move
  - {origin: "SEA", destination: "JFK", date: "2026-08-15"}
  - {origin: "LAX", destination: "ORD", date: "2026-09-03"}
```

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

