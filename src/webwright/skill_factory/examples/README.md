# Examples

Everything the Quickstart runs lives here, and nothing is hand-written — the library is
verbatim `learn` output.

```
examples/
├── quickstart.sh          # one command, every parameter pre-filled (demo, ask, solve)
├── flights.skill.yaml     # the example spec: build it to rebuild the library below
├── trajectories/          # 3 real solves — try `learn` without solving first (they expire)
├── solve_with_library.sh  # the solve wrapper: skill hint + answer-output instruction
├── learned_library/       # the Quickstart's artifact, checked in (skill.py + meta.json + replays.json)
│   └── what_is_the_earliest_nonstop_flight…/
├── tasks.example.json     # manual mode: a filled task list   (module README, step 6)
└── batch.example.json     # manual mode: a filled manifest    (module README, step 2)
```

## The checked-in skill

Three from-scratch solves of "earliest nonstop flight" on Google Flights (SEA→JFK,
SFO→BOS, LAX→ORD; 59, 25 and 40 agent steps) were grouped by
`python -m webwright.skill_factory learn --verify strict` into one template with **five**
lifted parameters, and the distilled skill reproduced all three training answers standalone
before it landed (`meta.json`: `verified: true, grade: executable`):

```json
{
  "template": "What is the earliest nonstop flight from {{origin_city}} ({{origin_code}}) to {{destination_city}} ({{destination_code}}) on {{date}} (one-way)? Return the answer as a list: [flight_number, airline, departure_time], ...",
  "signature": { "params": ["origin_city", "origin_code", "destination_city", "destination_code", "date"],
                 "call": "python skill.py taskspec.json" },
  "n_solves": 3, "verified": true, "grade": "executable"
}
```

Why this task: a flight *schedule* is a stable, client-independent fact the page states
plainly — so the answer is the same today, tomorrow, and on your machine, which is exactly
what lets `--verify strict` and standalone reuse mean something. On an unseen route
(SEA→DEN): from scratch 25–59 steps (the training spread), standalone **~40 s with no model**,
answer `["UA 2601", "United", "5:00 AM"]` — identical to an independent model-free probe.

## Run it

```bash
./quickstart.sh          # standalone, no API key, ~40 s
./quickstart.sh solve    # the agent reuses this skill on a new route (needs a key)
```

Manual mode (explicit manifests, gold gates): see the module README; the two
`*.example.json` files here are filled-in versions of the inputs it asks you to write.
