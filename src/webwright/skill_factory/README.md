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

## 🚀 Quick Start

**The task, throughout:** *what is the earliest nonstop flight from A to B on this date?* — on
the live Google Flights. Picked on purpose: a **schedule** is a fact the page states plainly, it
doesn't move on its own, and it reads the same on your machine as ours — which is what lets a
skill be replay-verified and reused standalone with a straight face. (The **fare** on the same
page would fail all three.) The checked-in library and its provenance:
[examples/](examples/).

**1. Run a learned skill** — no model, no API key, ~40 s. This is the whole pitch in one command:

```bash
cd src/webwright/skill_factory/examples
./quickstart.sh                            # the checked-in skill drives the live site
./quickstart.sh demo LAX ORD 2026-09-01    # ...on your own route
```

It prints the ten fixed steps it took and where it saved its screenshots — no model chose those
steps, they're the skill's code.

**2. Bring the agent in** — needs a key:

```bash
export OPENAI_API_KEY=...
./quickstart.sh ask     # one LLM call: "can the library help here?" -> use / adapt / skip
./quickstart.sh solve   # a full agent solve of an unseen route, reusing the checked-in skill
./quickstart.sh full    # the whole loop from nothing: 3 solves -> learn -> reuse (~40 min)
```

`demo` runs the skill; `ask` only *retrieves* — one round trip that shows what the agent is told
about the library, without solving anything; `solve` is the agent actually doing a task with it;
`full` rebuilds the library from scratch so you can watch it being made.

**3. Do it for *your* task** — this is the part that's yours, not the example's. Two ways in,
depending on whether you've solved the task yet:

**3a. You have a task you keep repeating, but no runs yet** — describe it, fill in your values,
build:

```bash
python -m webwright.skill_factory init "the cheapest <product> on Amazon, for any product"
$EDITOR skill.yaml     # fill the ____ values; check the guessed start_url

python -m webwright.skill_factory build skill.yaml --library ./library --jobs 3
#                                                       where it lands ↑    ↑ solve 3 at a time
```

`init` proposes the structure — a task template with `{holes}`, the site, and the verify mode
that fits your task — and leaves the values blank, because those are your ground truth, not the
model's guess. `build` fills the template with each instance, solves them, and hands the batch to
`learn`. Nothing runs until you say so: it prints the tasks it's about to solve and asks
(`--dry-run` just shows the plan), and a solve that already produced an answer is never
re-solved.

**`--jobs N` — how many instances to solve at once.** Solving is the slow half (10-30 min each)
and the instances are independent, so N of them run in parallel; N is yours to pick — any number,
default 1 (one after another). More than you have instances just means "all of them". What caps
it in practice isn't the flag, it's the site: too many browsers from one IP and you start getting
throttled, which looks like your skill failing when it's the site pushing back. 3-5 is a safe
place to start.

**3b. You already have a folder of webwright runs** — skip the solving, distil what's there:

```bash
python -m webwright.skill_factory learn outputs/ --library ./library
```

That's the day-to-day path once you're using Webwright anyway: the trajectories you produced
solving real work become the library, no spec to write.

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
**[docs/skill_factory/quickstart.md](../../../docs/skill_factory/quickstart.md)**

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

## 🚧 Limitations & Roadmap

Here are some known rough edges, and directions we might take them.

- **A skill can't outrun the agent that made it.** Everything is distilled from solves, so if the
  agent never figured out a good way to do something, there's nothing to distill. Pooling a bunch
  of failed attempts won't invent a strategy that was never there. The factory makes reuse cheap;
  it doesn't make hard tasks solvable.

- **The agent reaches for skills too eagerly.** Right now `decide` only asks "is there a relevant
  skill?", not "is using it actually worth it?" On WebArena it said `use` 49 times and `skip` not
  once, even on tasks that would've been quicker from scratch. It should weigh the two, and skip
  when starting fresh is the cheaper bet.

- **Reuse today is copy-and-edit, not a clean import.** The agent reuses a skill by reading the
  source and editing a copy, which is why `use` and `adapt` blur together in practice, and even a
  `use` can quietly rewrite half the code. A proper callable interface, where you import a skill
  and just pass it parameters, would make reuse a lot cleaner.

- **Verification is only as reliable as the reference answer it checks against.** On real websites, where no gold label is available, the LLM may misinterpret the task or produce an incorrect reference answer, and self-verification may fail to detect that error. For dynamic answers such as prices or rankings, verification often falls back to checking only the output format or structure. This can catch a skill that is broken or fails to execute, but not one that executes successfully and returns the wrong result. Achieving true correctness in these settings requires a stronger, independent judge, such as a WebJudge-style model.

- **Distillation is stochastic.** A given attempt may produce a fragile skill that fails even its own replay. The gate filters out these failures, and rerunning distillation a few times usually succeeds. However, each retry consumes additional tokens, so improving the reliability of executable skill generation—ideally succeeding on the first attempt—remains an important direction to explore.

- **Aggregation only groups by the literal template.** Ask the same task two different ways and
  you get two skills, each thinner than one merged one would be. Letting a model recognize when
  two wordings mean the same task would fix it.

- **The library needs upkeep, like any package registry.** After a skill lands, a site can shift
  under it with nothing re-checking, so it can quietly go stale and keep returning wrong answers.
  Stale skills never retire, and near-duplicate ones never get merged. Health checks, a retirement
  policy, and de-duplication are the obvious directions.

## 📚 Documentation

| doc | what's in it |
|---|---|
| [docs/skill_factory/quickstart.md](../../../docs/skill_factory/quickstart.md) | the complete tutorial: the flight-schedule loop, gateway knobs, standalone usage, measured costs |
| [docs/skill_factory/manual.md](../../../docs/skill_factory/manual.md) | manual mode: manifests field by field, gold gates, the batch pipeline |
| [docs/skill_factory/reference.md](../../../docs/skill_factory/reference.md) | verification & grades, every flag and env var, component map, backend |
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
