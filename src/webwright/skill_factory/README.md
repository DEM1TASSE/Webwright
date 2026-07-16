# Web Skill Factory

**Most agent skills are context the model refers to. Ours are programs.**
 
Every task Webwright solves leaves a working script behind. The Skill Factory turns those
scripts into a growing library of **reusable, verified, parameterized skills**: code you can
run without a model and compose into the next task instead of re-exploring the site.

## 🎥 Demo

https://github.com/user-attachments/assets/d15b1f83-2c8d-4f2d-bbc5-be365c0bcf4e

## ✨ Highlights
 
- 🏃 **Runs standalone, no model.** A learned skill is just code. It re-executes in ~30 s with zero tokens, so you can cron it to run every day, instead of having a model re-read a note and redo the work every time.
- 🛠️ **Has a real software-engineering surface.** Because skills are code, they inherit code's tools and properties for free: inheritance, polymorphism, encapsulation, tests, versioning, and history. A skill is executable and verifiable, not prose the model has to interpret.
- ✅ **Verified twice before it lands.** First an input gate: a solve only becomes material if it got the task right, so a wrong answer never feeds a skill. Then the distilled skill must replay its own answers standalone, with no model, so a broken skill can't slip in and poison the library.
- 🌱 **Gets stronger the more you use it.** New solves widen a skill in place, self-evolving as you go. Regression-replay keeps old coverage from breaking, so a skill that's already been verified is never damaged by a later change.


## How it compares
 
|  | published `SKILL.md`| SkillOpt | OpenCLI | **Web Skill Factory (Ours)** |
|---|---|---|---|---|
| a skill **is** | a document the model reads | a document the model reads | one CLI command per site capability | **a parameterized Python program that runs on its own, no model** |
| **domain / whose need** | anything, but nothing runs | general agent tasks (ALFWorld, DocVQA, spreadsheets, math...) | web: a site's common capabilities, shared by all users | **web: the specific task *you* repeat, including private, cross-site, multi-step workflows no shared catalogue has** |
| **produced by** | a person writes and publishes it; you install it | edits to one document, driven by past runs | a person or agent writes one per site | **distilling several solves of the same task template** |
| **parameters come from** | whoever wrote it | none | the author declares them | **the differences actually observed between your solves** |
| **verified?** | no | one gate: scores higher on a held-out split | one gate: checked when it's first written, plus live tests | **two gates: a wrong answer never feeds a skill, *and* the skill must reproduce its own answers standalone, no model** |
| agent can **adapt** it | read-only | read-only | it edits the source only to repair the shared adapter when it breaks — never to fit the task in front of it | **yes, per task: the source is in hand, to copy or to rework as the task needs — the library is left alone** |
| **grows from your runs** | no, it's whatever its author last wrote | yes, but what grows is a document for a frozen agent, not a program | no; a broken adapter is patched back to what it did, and nothing accumulates from your runs | **yes: each new solve widens it in place, regression-replayed so old coverage can't break** |

## 🗺️ How it works

![data flow & interfaces](../../../assets/skill_factory_pipeline.png)

```
solve → gate → group by template → distill → replay-verify → library → next solve reuses
```

At solve time the agent asks the library once and gets `use` / `adapt` / `skip` — its stated
intent for the skill, after which it has the source and reuses it as the task needs. Reuse never
blocks solving. Two touch points into Webwright, no agent-loop changes:

```bash
python -m webwright.tools.skill_use --task "<task>" --library ./library   # reuse at solve time
python -m webwright.skill_factory learn outputs/ --library ./library     # grow it afterwards
```

The commands, by what you already have:

| you have | command | what it does |
|---|---|---|
| a one-line need | `init "<need>"` | drafts `skill.yaml`: a task template, the site, the verify mode — values left for you |
| a filled `skill.yaml` | `build skill.yaml` | solves each instance, then hands the batch to `learn` |
| finished webwright runs | `learn outputs/` | gates them, distills, replay-verifies, grows the library |
| a benchmark, explicit golds | `update batch.json` | manual mode: every field yours — see [docs/manual.md](docs/manual.md) |

## 🚀 Quick Start

**1. Run a learned skill** — no model, no API key, ~40 s. This is the whole pitch in one command:

```bash
cd src/webwright/skill_factory/examples
./quickstart.sh                       # the checked-in skill drives a live site
./quickstart.sh demo LAX ORD 2026-09-01   # ...on your own route
```

It prints the ten fixed steps it took and where it saved its screenshots. The example is
*earliest nonstop flight* on Google Flights — a schedule is a stable, client-independent fact
the page states plainly, which is what makes `--verify strict` and standalone reuse mean
something.

**2. Watch the whole loop build that skill** — 3 solves → learn → reuse, ~40 min, needs a key:

```bash
export OPENAI_API_KEY=...
./quickstart.sh full
./quickstart.sh ask     # or just: ask the library about a task it has never seen
./quickstart.sh solve   # or: watch the agent reuse the checked-in skill on a new route
```

**3. Do it for *your* task** — this is the part that's yours, not the example's:

```bash
# you have a task you keep repeating -> draft a spec, fill in your values, build
python -m webwright.skill_factory init "the cheapest <product> on Amazon, for any product"
$EDITOR skill.yaml     # fill the ____ values; check the guessed start_url
python -m webwright.skill_factory build skill.yaml --library ./library --jobs 3

# you already have webwright runs lying around -> skip straight to distilling them
python -m webwright.skill_factory learn outputs/ --library ./library
```

`init` proposes the structure — a task template with `{holes}`, the site, and the verify mode
that fits your task — and leaves the values blank, because those are your ground truth, not the
model's guess. `build` fills the template with each instance, solves them, and hands the batch to
`learn`. Nothing runs until you say so: `build` prints the tasks it's about to solve and asks,
and `--dry-run` just shows the plan. A solve that already produced an answer is never re-solved.

<details>
<summary><b>On a custom OpenAI-compatible gateway</b> — two knobs, both needed</summary>

<br>

```bash
export OPENAI_ENDPOINT=... OPENAI_MODEL=...   # for learn / init / skill_use
export MODEL_CFG=/abs/path/to/model.yaml      # for the AGENT in solve/build
```

The endpoint is the FULL `.../responses` URL, not a base path. The agent reads its model from a
yaml, not from these env vars — copy `examples/model_gateway.example.yaml` and point `MODEL_CFG`
at it (or pass `-c` to `build`).

</details>

Full tutorial — the loop spelled out, gateway setup, running skills without the agent:
**[docs/quickstart.md](docs/quickstart.md)**

## 📊 Results

**Setting.** WebArena, 10 retrieve-type task templates across 3 self-hosted sites
(shopping-admin, gitlab, map). Each template contributes 3 train solves that build the library
(gated on ground-truth answers) and 2 held-out instances that measure reuse on unseen instances
of the same template. Every task is solved both with the library and from scratch. Model:
gpt-5.4. 100 runs in total.

|                         | WITH library | from scratch |    Δ    |
|-------------------------|--------------|--------------|---------|
| held-out accuracy (20)  | **70%**      | 55%          | **+15 pp** |
| held-out avg steps      | **14.7**     | 17.1         | −2.4    |
| train accuracy (30)     | **86.7%**    | 76.7%        | +10 pp  |
| train avg steps         | **13.7**     | 15.9         | −2.2    |

- **Reuse helps most when solving from scratch is expensive.** Of 20 held-out tasks, 4 were
  rescued (they failed from scratch and the library solved them) and 6 more solved in fewer
  steps. The +15pp is measured on instances that never took part in building the library; the
  same direction holds on training instances (86% vs 76%).
- **Biggest single win:** a task that took 33 steps from scratch ran in 10 with the library.
- **Wrong solves stay out.** 7 of 30 train solves failed the ground-truth gate and never
  entered the library.
- **Retrieval stayed reliable as the library grew** to 10 skills: all 20 held-out solves
  retrieved their own template's skill, including two near-duplicate gitlab commit skills.

**How to read it.** In the agent-in-loop path (a `reference` skill the agent reads and reuses,
which is what the eval runs), step savings scale with how much the agent doesn't already know:
on a familiar site the cost of querying the library and reading the skill can outweigh what it
saves, so reuse pays off most on the hard tasks. From-scratch cost is also high-variance, and a
skill pins the strategy down.
 
An `executable` skill skips that path entirely: it runs standalone, with no agent and no model
in the loop, in a fixed handful of steps, so every repeat after the first is essentially free.
(Results on this mode coming soon.)

## ⚠️ Limitations & Roadmap

- **A skill can't outrun the agent that made it.** Everything in the library was distilled from
  solves; if the agent never found a good strategy for a task, no amount of aggregating its
  attempts will invent one. The factory makes reuse cheap and reliable — it doesn't raise the
  ceiling on what can be solved in the first place.
- **`decide` reaches for the library too eagerly.** It judges whether a skill is *relevant*, not
  whether reusing it is *worth it*, so on the WebArena run it answered `use` 49 times and `skip`
  zero — including tasks that would have been cheaper from scratch. It should weigh the cost of
  solving fresh against the cost of reading and fitting a skill.
- **Verification is only as strong as the task's ground truth.** Stable, page-stated facts
  (schedules) earn real `--verify strict`; answers that drift on their own — prices, stock,
  rankings — fall back to a shape check, which catches a broken skill but not a wrong one. Real
  correctness needs `--golds`, and today choosing a verifiable task or supplying golds is on you.
  Wiring in an independent judge (WebJudge-style, or cross-source agreement) would lift that.
- **Not every batch yields an `executable` skill.** Distillation is stochastic: a draw can come
  out brittle and fail its replay. That's the gate working — nothing unproven lands, and the
  solves stay retryable — and `--on-fail reference` keeps the attempt as a readable prior rather
  than nothing. But the `reference` grade has not been evaluated on its own: we know an
  `executable` skill is worth 70% vs 55%; we don't yet have a number for what a `reference`
  skill is worth to an agent.
- **Aggregation stops at the literal template.** Solves group into one skill only when they share
  a template string, so the same underlying task asked two ways — "the cheapest flight" and
  "which flight costs least" — becomes two skills, each thinner than one merged skill would be.
  Semantic grouping (an LLM deciding when different wordings mean the same task) is the obvious
  next step, and it needs a stronger admission bar with it: merging tasks that only *look* alike
  would quietly poison a skill.
- **Strict replay runs against the live site, not a recorded page**, so it's a fair bar only when
  `learn` closely follows the solves; deterministic offline replay from recorded traces is
  planned. And nothing watches a skill after it lands — a site can drift under a verified skill
  and no one finds out until it's used.

## 📚 Documentation

| doc | what's in it |
|---|---|
| [docs/quickstart.md](docs/quickstart.md) | the complete tutorial: the flight-schedule loop, gateway knobs, standalone usage, measured costs |
| [docs/manual.md](docs/manual.md) | manual mode: manifests field by field, gold gates, the batch pipeline |
| [docs/reference.md](docs/reference.md) | verification & grades, every flag and env var, component map, backend |
| [examples/README.md](examples/README.md) | the checked-in skill and the example inputs |

## 📝 Citation

```bibtex
@misc{web_skill_factory,
  title  = {Web Skill Factory: Evolving Reusable, Verified, Code-Native Skills for Web Agents},
  author = {Demi Ruohan Wang, Yadong Lu},
  year   = {2026},
  note   = {Built on Webwright},
  url    = {https://github.com/microsoft/Webwright}
}
```
