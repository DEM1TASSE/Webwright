# Web Skill Factory

**Most agent skills are context the model refers to. Ours are programs.**

Each solved task becomes runnable, parameterized code — verify it, run it without the
model, and import it into the next task instead of re-exploring.

Module: `webwright.skill_factory`, built on Webwright.

## 🎥 Demo

https://github.com/user-attachments/assets/d15b1f83-2c8d-4f2d-bbc5-be365c0bcf4e

## ✨ Why

- 🧩 **Import, don't just refer** — skills are executable code; a learned skill re-runs
  standalone in ~30 s with **no model in the loop**
- 🌱 **Self-evolving** — each batch of solves is gated, grouped by template, distilled;
  wrong answers never enter, working skills never break
- ✅ **Replay-verified** — a skill must reproduce its own training answers standalone
  before it may land
- 💸 **Cheap to adopt** — one tool + one CLI, zero agent-loop changes

## 🗺️ How it works

![data flow & interfaces](../../../assets/skill_factory_pipeline.png)

```
solve → gate → group by template → distill → replay-verify → library → next solve reuses
```

At solve time the agent asks the library once and gets `use` / `adapt` / `skip` —
reuse never blocks solving.

## 🚀 Quick Start

```bash
cd src/webwright/skill_factory/examples
./quickstart.sh        # a learned skill drives a live site — no model, no API key needed
```

<details>
<summary><b>More modes</b> — reuse with the agent, or rebuild the library yourself</summary>

<br>

```bash
export OPENAI_API_KEY=...
./quickstart.sh ask      # ask the library about a task it has never seen
./quickstart.sh solve    # the agent REUSES the checked-in skill on a new route
./quickstart.sh full     # the whole loop: 3 solves -> learn -> reuse (~30 min)
```

On a custom OpenAI-compatible gateway, also `export OPENAI_ENDPOINT=... OPENAI_MODEL=...`
(for learn / skill_use) and `export MODEL_CFG=/path/to/your_model.yaml` (for the agent).

</details>

Full tutorial — the loop spelled out, gateway setup, running skills without the agent:
**[docs/quickstart.md](docs/quickstart.md)**

## 💰 What it costs (measured)

Same unseen route, minutes apart:

|           | from scratch | with the library | the skill, standalone |
|-----------|--------------|------------------|-----------------------|
| steps     | 17           | 15               | — (no agent)          |
| wall time | 8.9 min      | **5.2 min**      | **32 s, no model**    |

Exploration is paid once — standalone repeats need no model at all.

## 📊 Results

**Setting** — WebArena, 10 retrieve-type task templates across 3 self-hosted sites
(shopping-admin, gitlab, map). Per template: 3 train solves build the library
(gold-gated), 2 held-out instances measure reuse; every held-out task is solved both
WITH the library and from scratch. Same model, same budget, 100 solves total.

|                         | WITH library | from scratch |    Δ    |
|-------------------------|--------------|--------------|---------|
| held-out accuracy (20)  | **70%**      | 55%          | **+15 pp** |
| held-out avg steps      | **14.7**     | 17.1         | −2.4    |
| train accuracy (30)     | **86.7%**    | 76.7%        | +10 pp  |
| train avg steps         | **13.7**     | 15.9         | −2.2    |

- **4 held-out tasks rescued** (wrong → correct); net reuse-wins vs regressions **7 : 1**;
  biggest win **33 → 10 steps**
- retrieval stayed reliable as the library grew: all 20 held-out solves picked the right
  skill, including two near-duplicate templates
- mixed-template batches evolve safely: adds, refines and keeps with zero cross-contamination

## 🧠 Design

**Actions are already code.** Webwright solves by writing code — every solve leaves a
working script behind, so skills are a byproduct, not an instrumentation layer. It
complements `crafted_cli`: craft parameterizes one script by *anticipating* what might
vary; the factory parameterizes across solves from the differences *actually observed*.

**One solve isn't a skill yet.** A single script is correct but narrow. Aggregating
verified solves of the same template turns observed differences into parameters and
recurring patterns into primitives — different runs' strategies become fallbacks, and
what lands is the best algorithm the solves discovered.

**Growth never breaks what works.** New templates add skills, new solves refine existing
ones in place (regression-replayed against their stored training examples), untouched
skills stay byte-identical.

## 🔌 Plugs into Webwright

Two touch points, no agent-loop changes:

```bash
python -m webwright.tools.skill_use --task "<task>" --library ./library   # reuse at solve time
python -m webwright.skill_factory learn outputs/ --library ./library     # grow it afterwards
```

## 📚 Documentation

| doc | what's in it |
|---|---|
| [docs/quickstart.md](docs/quickstart.md) | the complete tutorial: the flights loop, gateway knobs, standalone usage, measured costs |
| [docs/manual.md](docs/manual.md) | manual mode: manifests field by field, gold gates, the batch pipeline |
| [docs/reference.md](docs/reference.md) | verification & grades, every flag and env var, component map, backend |
| [examples/README.md](examples/README.md) | the checked-in skill and the example inputs |
