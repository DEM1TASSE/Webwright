# Quickstart — the complete tutorial

[← back to the module README](../README.md)

Three steps: solve a few instances of a task type, `learn` them into a skill, then watch
the next solve reuse it. Solves are long tasks (10-30 min each) — if your shell or tooling
enforces command timeouts, run them in the background. The task family is Google Flights
(the site from Webwright's own README): *what is the earliest nonstop flight on this route
and date?* A flight schedule is a stable, client-independent fact the page states plainly —
so the answer is the same today, tomorrow, and on your machine, which is exactly what lets a
learned skill be replay-verified (`--verify strict`) and reused standalone with a straight
face. The UI is still genuinely fiddly (trip type, airport autocomplete, date picker, the
nonstop filter), so the skill has something real to carry.

**Fastest path — one command, every parameter pre-filled:**

```bash
cd src/webwright/skill_factory/examples
./quickstart.sh          # a learned skill drives the live site — no model, no API key needed
./quickstart.sh ask      # ask the library about a task it has never seen   (needs a key)
./quickstart.sh solve    # watch the agent REUSE the checked-in skill        (needs a key)
./quickstart.sh full     # rebuild the library yourself: 3 solves -> learn -> reuse (~40 min)
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

`learn` scans the run folders, gates each solve (gold if you pass `--golds golds.json`,
else a shape check), auto-groups tasks into templates with one LLM call per ~25 runs,
extracts the parameters, and grows the library. It is **idempotent** — re-run it whenever;
already-learned runs are skipped (`library/.learned.json`), and big folders are chunked
automatically. `--dry-run` shows the grouping plan without changing anything. Every new skill
must **replay standalone and reproduce its own training answers** before it lands (see the gate
section; use `--verify strict` for stable-fact families like this one, `--verify shape` for
live-data families whose answer legitimately drifts).
Everything below is **manual mode** — explicit manifests, benchmark-grade gold gates, fine
control over every field. You don't need it to get started.

**Where this fits:**
- *recurring personal queries* — releases, commit counts, price checks: pay the exploration
  once, every repeat is cheap (or free — run the skill standalone from cron, no model);
- *same-template batch jobs* — QA flows, report pulls: solve 3, learn, run the rest on skills;
- *a team library* — commit `./library` to your repo; everyone's agent reuses it.

