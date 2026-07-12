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

WebArena, 10 templates × 3 sites, held-out instances:

- accuracy **70% vs 55%**, 4 tasks rescued (wrong → correct)
- biggest win **33 → 10 steps**, net reuse-wins vs regressions **7 : 1**

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
| [docs/verification.md](docs/verification.md) | the gate, replay verification, executable vs reference grades |
| [docs/architecture.md](docs/architecture.md) | design rationale, component map, backend abstraction |
| [docs/evaluation.md](docs/evaluation.md) | WebArena results in detail, retrieval reliability, honest caveats |
| [examples/README.md](examples/README.md) | the checked-in skill and the example inputs |
