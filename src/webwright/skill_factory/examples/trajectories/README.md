# Three solved runs, so you can try `learn` without solving first

`learn` is the day-to-day path — you've been using Webwright anyway, so hand it the runs you
already have. But that's hard to *try* if you've never run Webwright: you'd have to spend 30
minutes solving before you had anything to distil. These are three real solves of the flights
template, so you don't have to:

```bash
cd src/webwright/skill_factory/examples
python -m webwright.skill_factory learn trajectories --library ./library
```

Three runs → one template → five lifted parameters → one skill, replay-verified before it lands.
Needs an API key (the grouping and distillation are model calls). Takes ~5-13 minutes, and **may
reject on the first attempt** — that's the gate, not a misconfiguration; run it again. See
[What to expect](../../README.md#what-to-expect).

## What's here, and what isn't

`learn` reads exactly three files per run, so that's all we ship:

| file | what it's for |
|---|---|
| `task.json` | the task text and start_url — the template is inferred from these |
| `final_script.py` | the working script the agent wrote — the raw material distillation aligns |
| `agent_response.json` | the answer it got — the baseline replay-verify has to reproduce |

The full run directories were ~12 MB each, almost all screenshots; none of that is read. The
absolute library path the solving machine had in its prompt has been scrubbed.

## ⚠️ These expire

The runs are pinned to **2026-08-15**, and their answers were true on 2026-07-15:

| route | answer |
|---|---|
| SEA→JFK | `["AS26", "Alaska", "7:00 AM"]` |
| SFO→BOS | `["B6 434", "JetBlue", "6:00 AM"]` |
| LAX→ORD | `["UA 729", "United", "12:10 AM"]` |

`--verify strict` (the default) replays the skill against the **live** site and demands these
answers back. So:

- **if an airline reschedules**, the replay returns a different flight and the skill is rejected;
- **once 2026-08-15 is in the past**, Google Flights can't show that date at all, the skill
  crashes rather than answers, and it is rejected.

Neither is a bug in the pipeline — it's a fixture with a shelf life, and this is what the shelf
life looks like. `--verify shape` does **not** rescue the second case: a crashed skill writes no
answer, and shape still requires a non-empty one.

To see the distillation half after they've gone stale, `--verify off` skips the replay entirely
(and lands an unverified skill — fine for a demo, not for a library you trust). To get the whole
loop back, re-solve with a live date: `build flights.skill.yaml` after moving its `date`.
