# Quickstart — the complete tutorial

[← back to the module README](../README.md)

Three steps: solve a few instances of a task type, `learn` them into a skill, then watch
the next solve reuse it. Solves are long tasks (5-30 min each) — if your shell or tooling
enforces command timeouts, run them in the background. The task family is the one from Webwright's main README —
Google Flights — where the answer is live (no model can recall it) and the UI is genuinely
fiddly, so a learned skill has something real to carry.

**Fastest path — one command, every parameter pre-filled:**

```bash
cd src/webwright/skill_factory/examples
./quickstart.sh          # a learned skill drives the live site — no model, no API key needed
./quickstart.sh ask      # ask the library about a task it has never seen   (needs a key)
./quickstart.sh solve    # watch the agent REUSE the checked-in skill        (needs a key)
./quickstart.sh full     # rebuild the library yourself: 3 solves -> learn -> reuse (~30 min)
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
while IFS='|' read -r FROM TO; do
  examples/solve_with_library.sh \
    "What is the cheapest flight from $FROM to $TO on 2026-08-15 (one-way)? Return the answer as a list: [airline, price]." \
    https://www.google.com/flights "$PWD/library" -o outputs -c base.yaml -c model_openai.yaml
done <<'ROUTES'
Seattle (SEA)|New York (JFK)
San Francisco (SFO)|Boston (BOS)
Los Angeles (LAX)|Chicago (ORD)
ROUTES

# 2. LEARN: distill everything you've solved into skills — no manifest, no fields to fill
python -m webwright.skill_factory learn outputs/ --library ./library
# -> groups the 3 runs into ONE template and lifts FIVE parameters:
#    origin city/code, destination city/code, date
#    library/what_is_the_cheapest_flight_from_origin_.../{skill.py, meta.json}

# 3. USE the library: same wrapper, an UNSEEN route — the agent finds and reuses the skill
examples/solve_with_library.sh \
  "What is the cheapest flight from Seattle (SEA) to Denver (DEN) on 2026-08-15 (one-way)? Return the answer as a list: [airline, price]." \
  https://www.google.com/flights "$PWD/library" -o outputs -c base.yaml -c model_openai.yaml
# outputs/<run>/skill_decision.json -> {"verdict": "use", "skill_id": "what_is_the_cheapest_..."}
```

The library is also usable **without the agent** — this is the whole point of code skills:

```bash
# ask it whether it can help a task (the same call the agent makes — one LLM round trip)
python -m webwright.tools.skill_use \
  --task "cheapest flight from Portland (PDX) to Austin (AUS) on 2026-09-01" \
  --library ./library

# or run the learned skill directly — no model in the loop, ~30 seconds
SKILL=$(ls "$PWD"/library/what_is_the_cheapest_flight_*/skill.py)
cd "$(mktemp -d)"    # scratch dir: the skill writes its artifacts to the cwd
cat > taskspec.json <<'EOF'
{"params": {"origin_city": "Seattle", "origin_code": "SEA", "destination_city": "Denver",
            "destination_code": "DEN", "date": "2026-08-15"},
 "output_schema": {"type": "array", "items": {"type": "string"}}}
EOF
python "$SKILL" taskspec.json
# -> {"retrieved_data": ["Frontier", "$68"]}   (live price — yours will differ)
```

**What each way of running it actually costs** — the same unseen route (SEA→DEN), measured
minutes apart:

|                | from scratch | with the library | the skill, standalone |
|----------------|--------------|------------------|-----------------------|
| steps          | 17           | 15 (verdict `use`) | — (no agent)         |
| wall time      | 8.9 min      | **5.2 min**      | **32 s**              |

How to read it: step savings scale with **how much the agent doesn't already know**. On a
site the model can drive from memory, the gap is small (17→15 here) — but from-scratch cost
is high-variance (our three training routes took 13, 18 and 26 steps for the *same* task
type), and the skill pins down the strategy, cutting that spread. Where the agent genuinely
doesn't know what to do, reuse is the difference between exploring and executing — on
WebArena's unfamiliar self-hosted sites it's 33→10 steps and wrong→correct (numbers above).
Wall time drops even here (exploration steps load pages and ship them to the model; reuse
steps run known code). And the last column is the structural win: **every repeat after the
first runs with no model at all** — a fare watcher in cron pays ~9 minutes of agent work
once, then ~30 s forever.

**Verification on live data, honestly:** flight prices have no fixed gold answer, so the
gate here is `self_verify` — shape plus the agent's own SUCCESS report; the run-time warning
spells out what that does and doesn't catch. What the table
DOES verify: three independent paths to the same answer, minutes apart. When your task
family has golds, pass `--golds` and admission becomes real verification.

Exactly this loop, already run and checked in: `examples/learned_library/` (provenance in
`examples/README.md`).

`learn` scans the run folders, gates each solve (gold if you pass `--golds golds.json`,
else a shape check), auto-groups tasks into templates with one LLM call per ~25 runs,
extracts the parameters, and grows the library. It is **idempotent** — re-run it whenever;
already-learned runs are skipped (`library/.learned.json`), and big folders are chunked
automatically. `--dry-run` shows the grouping plan without changing anything. Every new skill
must **replay standalone and reproduce its own training answers** before it lands (see the gate
section; `--verify shape` for live-data families like the flights example).
Everything below is **manual mode** — explicit manifests, benchmark-grade gold gates, fine
control over every field. You don't need it to get started.

**Where this fits:**
- *recurring personal queries* — releases, commit counts, price checks: pay the exploration
  once, every repeat is cheap (or free — run the skill standalone from cron, no model);
- *same-template batch jobs* — QA flows, report pulls: solve 3, learn, run the rest on skills;
- *a team library* — commit `./library` to your repo; everyone's agent reuses it.

