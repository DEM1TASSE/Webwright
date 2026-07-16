# Web Skill Factory

**Most agent skills are context the model refers to. Ours are programs.**

Every task Webwright solves leaves a working script behind. The factory turns those scripts
into a growing library of **reusable, verified, parameterized skills** — code you can run
without a model, import like a package, and compose into the next task instead of
re-exploring the site.

Module: `webwright.skill_factory`, built on Webwright.

## 🎥 Demo

https://github.com/user-attachments/assets/d15b1f83-2c8d-4f2d-bbc5-be365c0bcf4e

## Overview

A skill here is a **program**, not a note the model reads back. That one choice is the whole
pitch, and it buys three things a text playbook can't:

- 🧩 **Runs standalone, no model in the loop.** A learned skill re-executes in ~40 s with zero
  tokens. A schedule watcher in cron pays for agent exploration once, then runs for free forever.
- 📦 **Imports like a library.** The unit of reuse is a callable file with a typed signature —
  `python skill.py taskspec.json` — not a paragraph you paste into a prompt and hope the model
  follows.
- 🛠️ **Has a software-engineering surface.** Because skills are code, they get code's tools:
  diff them, version them, test them, review them in a PR. A skill's behavior is inspectable and
  pinned, not re-improvised on every call.

**How a good skill actually gets made** — a program you can trust doesn't fall out of one solve:

- 🎯 **One solve is correct but narrow.** A single script hard-codes one route, one date, one
  path. The factory aggregates *many instances of the same template* so the differences it
  actually observed between solves become **parameters**, and the recurring core becomes reusable
  **primitives** (`set_route()`, `apply_nonstop_filter()`, `extract_rows()`) — a thin task layer
  on top. Different solves' strategies survive as fallbacks; what lands is the best algorithm the
  solves discovered, not any single run.
- 🧱 **Primitives compose.** The expensive parts — login, navigation, extraction — are factored
  once and reused across tasks even when the final step differs, so the library gets *cheaper to
  extend* as it grows, not more tangled.
- ✅ **Nothing lands unverified — an unproven skill would poison the library.** Distillation can
  introduce bugs, and an agent reading a broken skill as source will quietly work around them, so
  agent-in-the-loop success can't certify a skill. The proof is model-free: a candidate must
  **replay its own training taskspecs standalone and reproduce the answers** before it may land.
  Every skill carries its grade — `executable` (proved) or `reference` (a prior the agent may
  read but not trust). Failed refinements never overwrite a working skill.
- 🌱 **Self-evolving, batch by batch.** Each batch of solves is gated, grouped by template, and
  distilled: new templates add skills, new solves refine existing ones **in place**
  (regression-replayed against their stored training examples), wrong answers never enter, and
  untouched skills stay byte-identical.

### How it compares

|                                   | NL skill notes | recorded macros | learned NL skill libs | **Web Skill Factory** |
|-----------------------------------|:--------------:|:---------------:|:---------------------:|:---------------------:|
| a skill *is*…                     | text the model reads | a fixed click trace | text the model reads | **executable code** |
| runs without the model            | ✗              | ~ (brittle)     | ✗                     | **✓** |
| generalizes across inputs         | model re-reasons | ✗ (hard-coded) | model re-reasons      | **✓ (lifted params)** |
| composable primitives             | ✗              | ✗               | ~                     | **✓** |
| verified before it's reused       | ✗              | ✗               | rarely                | **✓ replay-verified** |
| self-evolving library             | ✗              | ✗               | ✓                     | **✓** |

*(Columns are categories, not specific products — swap in the exact repos you're comparing
against; the axes are what matter.)*

## 🗺️ How it works

![data flow & interfaces](../../../assets/skill_factory_pipeline.png)

```
solve → gate → group by template → distill → replay-verify → library → next solve reuses
```

At solve time the agent asks the library once and gets `use` / `adapt` / `skip` — reuse never
blocks solving. Two touch points, no agent-loop changes:

```bash
python -m webwright.tools.skill_use --task "<task>" --library ./library   # reuse at solve time
python -m webwright.skill_factory learn outputs/ --library ./library     # grow it afterwards
```

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
./quickstart.sh full     # the whole loop: 3 solves -> learn -> reuse (~40 min)
```

On a custom OpenAI-compatible gateway, also `export OPENAI_ENDPOINT=... OPENAI_MODEL=...`
(for learn / skill_use; the endpoint is the FULL `.../responses` URL, not a base path) and
`export MODEL_CFG=...` pointing at a copy of `examples/model_gateway.example.yaml` (for the
agent — it reads a yaml, not these env vars).

</details>

The checked-in example is *earliest nonstop flight* on Google Flights — a schedule is a stable,
client-independent fact the page states plainly, so the answer is the same tomorrow and on your
machine, which is exactly what makes `--verify strict` and standalone reuse mean something.

Full tutorial — the loop spelled out, gateway setup, running skills without the agent:
**[docs/quickstart.md](docs/quickstart.md)**

## 📊 Results

**Setting** — WebArena, 10 retrieve-type task templates across 3 self-hosted sites
(shopping-admin, gitlab, map). Per template: 3 train solves build the library (gold-gated),
2 held-out instances measure reuse; every held-out task is solved both WITH the library and
from scratch. Same model, same budget, 100 solves total.

|                         | WITH library | from scratch |    Δ    |
|-------------------------|--------------|--------------|---------|
| held-out accuracy (20)  | **70%**      | 55%          | **+15 pp** |
| held-out avg steps      | **14.7**     | 17.1         | −2.4    |
| train accuracy (30)     | **86.7%**    | 76.7%        | +10 pp  |
| train avg steps         | **13.7**     | 15.9         | −2.2    |

- **4 held-out tasks rescued** (wrong → correct); net reuse-wins vs regressions **7 : 1**;
  biggest win **33 → 10 steps**
- retrieval stayed reliable as the library grew: all 20 held-out solves picked the right skill,
  including two near-duplicate templates
- on the live-site example, the learned skill runs an unseen route in **10 fixed steps / ~40 s /
  0 model calls**, versus 25–59 from-scratch steps for the same task type — and its answer is
  byte-identical to an independent model-free probe of the page

**How to read it:** step savings scale with *how much the agent doesn't already know*. On a
familiar site the gap is small; the structural win is that **every repeat after the first runs
with no model at all**, and that from-scratch cost is high-variance while a skill pins the
strategy down.

## ⚠️ Limitations & Roadmap

- **Verification is only as strong as the task's ground truth.** Stable, page-stated facts
  (schedules) earn real `--verify strict`. Families whose answer legitimately drifts — live
  prices, inventory — fall back to a shape check or need `--golds`. Choosing a verifiable task,
  or supplying a golds source, is on the user.
- **Strict replay runs against the live site, not a recorded page** — so it's a fair bar only
  when `learn` closely follows the solves. Deterministic offline replay from recorded traces is
  planned.
- **Cross-client robustness.** A skill learned on one machine can meet different initial page
  state elsewhere (locale, prefilled fields). The framework favors loud failure over silent
  fallback, but hardening form interaction across clients is ongoing.
- **Scope.** Results are 10 WebArena retrieve templates plus one live-site family; broader task
  types, larger libraries, and an independent judge (WebJudge / cross-source checks) for a truly
  model-free gate are future work.

## 📚 Documentation

| doc | what's in it |
|---|---|
| [docs/quickstart.md](docs/quickstart.md) | the complete tutorial: the flight-schedule loop, gateway knobs, standalone usage, measured costs |
| [docs/manual.md](docs/manual.md) | manual mode: manifests field by field, gold gates, the batch pipeline |
| [docs/reference.md](docs/reference.md) | verification & grades, every flag and env var, component map, backend |
| [examples/README.md](examples/README.md) | the checked-in skill and the example inputs |

## 📝 Citation

```bibtex
@software{web_skill_factory,
  title  = {Web Skill Factory: Evolving Reusable, Verified, Code-Native Skills for Web Agents},
  author = {TODO},
  year   = {2026},
  note   = {Built on Webwright},
  url    = {https://github.com/microsoft/Webwright}
}
```
