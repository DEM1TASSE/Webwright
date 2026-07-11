# Examples

Everything the Quickstart runs lives here, and nothing is hand-written — the library is
verbatim `learn` output.

```
examples/
├── quickstart.sh          # one command, every parameter pre-filled (demo, ask, solve, full)
├── solve_with_library.sh  # the solve wrapper: skill hint + answer-output instruction
├── learned_library/       # the Quickstart's artifact, checked in (skill.py + meta.json)
│   └── what_is_the_cheapest_flight…/
├── tasks.example.json     # manual mode: a filled task list   (module README, step 6)
└── batch.example.json     # manual mode: a filled manifest    (module README, step 2)
```

## The checked-in skill

Three from-scratch solves of "cheapest one-way flight" on Google Flights (SEA→JFK,
SFO→BOS, LAX→ORD; 13, 26 and 18 agent steps) were grouped by
`python -m webwright.skill_factory learn` into one template with **five** lifted
parameters:

```json
{
  "template": "What is the cheapest flight from {{origin_city}} ({{origin_code}}) to {{destination_city}} ({{destination_code}}) on {{date}} (one-way)? ...",
  "signature": { "params": ["origin_city", "origin_code", "destination_city", "destination_code", "date"],
                 "call": "python skill.py taskspec.json" },
  "n_solves": 3
}
```

Measured on an unseen route (SEA→DEN), minutes apart: from scratch 17 steps / 8.9 min,
with the library 15 steps / 5.2 min (verdict `use`), standalone ~30 s with **no model** —
all three answers identical.

## Run it

```bash
./quickstart.sh          # standalone, no API key, ~30 s
./quickstart.sh solve    # the agent reuses this skill on a new route (needs a key)
```

Manual mode (explicit manifests, gold gates): see the module README; the two
`*.example.json` files here are filled-in versions of the inputs it asks you to write.
