# skill_agent — the audited build pipeline, driven by a terminal agent

The scripted pipeline (`webwright.skill_factory.audited_primitive_build`) builds a site primitive
library with four `llm_json` calls wired together by a Python loop. The model never sees the
source workflow as a file, never runs the validator, and never decides what happens next.

Here the agent owns the procedure. It gets a bash workspace, the real source scripts on disk, the
rules as documents it reads when it needs them, and one command. It decides what to do next and
when the work is finished.

The validators, batching, apply/consolidate logic, and output layout are imported unchanged, so
an agentic library and a scripted library are directly diffable.

## Who decides what

| | scripted | agentic |
|---|---|---|
| Order of work | a Python loop calls four prompts in sequence | the agent follows a procedure and decides what to do next |
| Sees the source workflow | as a JSON string in the prompt | as `in/sources/<id>.py`, greppable, parseable, runnable |
| The rules | four system prompts, all loaded up front | `in/rules/*.md`, read at the step they govern |
| Validator feedback | injected into the next prompt | a command the agent runs as often as it likes |
| Emitting a primitive | one giant JSON with Python escaped inside a string | one file per operation + real `.py` method bodies |
| Quality gate | a second `llm_json` call in the same driver loop | a fresh judge episode, spawned inside `verify` |
| Committing to the library | the driver, implicitly | the driver, only after `verify` passes on its own re-run |

The driver still exists, but only for what an agent must not be trusted with: what goes into a
workspace, whether the result actually verifies, and the mechanical write itself. An episode
that does not verify is retried; the agent's word that it finished is never taken.

## Two episode levels

The split follows where the pipeline's own context boundary falls:

- **batch** — extract every workflow in the batch, then build primitives that survive the judge.
  Sees this batch's source code (~10k tokens at the current batch size) and the pool so far.
- **site** — consolidate the accumulated pool. Sees the pool
  (~10k tokens for the largest site), not the raw workflows it came from.

One episode for everything would put all 17 workflows plus every intermediate artifact in a
single context; one episode per artifact is what the scripted pipeline already did.

## One command

```bash
python -m skill_agent.verify
```

That is the whole surface the agent has. It reports what the episode still owes, composes
`out/ops/*.json` + `out/code/*.py` into a proposal, validates everything, and — once the
structure is clean — submits the proposal to an independent judge. Exit 0 means done.

Composition is not a convenience: a site proposal carrying several primitives' full method
bodies does not fit in one model response, so the work has to be written as small files and
assembled.

The judge is a **separate agent with an empty context** that reads the proposed code and the
evidence it cites and rules PASS/FAIL per operation. Independence is the point — letting the
author grade its own work loses exactly what this catches. Verdicts are cached against the
proposal hash, so re-verifying unchanged work does not spawn another judge.

Applying operations and rendering the package are deliberately **not** commands. They involve
no judgement, so they belong to the driver, which re-runs `verify` itself before writing
anything to the library.

## Workspace contract

```
in/context.json      {mode, site, batch, pool, all_workflows, …}
in/sources/*.py      gold final_script.py behind each workflow
in/code/*.py         pooled method bodies, as real Python
in/rules/*.md        the boundary rules for the steps in this episode
in/previous_attempt_feedback.json   only if an earlier attempt was rejected
out/extractions/<workflow_id>.json
out/ops/*.json + out/code/*.py  ->  out/proposal.json
out/verdicts.json    written by the judge episode `verify` spawns, cached by proposal hash
```

Episode state the commands resolve through `skill_agent.context`: `SKILL_AGENT_LIBRARY`,
`SKILL_AGENT_BATCH`, `SKILL_AGENT_MODEL_CONFIG`, `SKILL_AGENT_REPO_ROOT`.

## Running it

```bash
set -a && . /path/to/webwright/.env && set +a      # OPENAI_API_KEY for the gateway

PYTHONPATH=src:. python -m skill_agent.build \
    --workflows skill_agent/inputs/workflows \
    --output runs/agentic_v1 \
    --model-config /path/to/model_gateway_54.yaml \
    --sites map
```

Resumable: an applied batch and a rendered site are skipped on re-run.

## Inputs are frozen

The scripted build resolved its sources at build time from a manifest pointing at untracked
`<run_dir>/final_script.py` files, so a build only reproduced on the machine that produced those
runs. `skill_agent/inputs/workflows/<site>.json` is a self-contained snapshot — code inlined,
`MANIFEST.json` recording each source's `record_path` and code SHA256.

The current snapshot is the same 17 gold-admitted workflows behind `audited_site_library_v2`:
GitLab 7, Shopping 4, Map 3, Shopping Admin 3. Re-freeze with:

```bash
python -m skill_agent.tools.snapshot_inputs --from-library <library_dir> --output skill_agent/inputs
python -m skill_agent.tools.snapshot_inputs --manifest m.json --dataset d.json --output skill_agent/inputs
```

## Output

Same layout as the scripted build — `config.json`, `workflow_order.json`, `extractions/`,
`batches/batch_NNN/{proposal,validation,quality_verdicts,primitive_diff,snapshot}`,
`pre_consolidation/`, `consolidation/{proposal,coverage}`,
`final_candidate/{package.py,index.json,review.md}`, `audit.json` — plus `pool.json` carrying the
live pool between batch episodes, and `agent_runs/` holding every episode workspace and
`trajectory.json` (including each judge episode under `.judge/`).

## Generated code must parse before 3.12

PEP 701 lets an f-string reuse its own quote inside an expression: `f'{p['lon']}'`. That is a
SyntaxError on 3.11 and earlier, and across three real runs the agent never once wrote it — the
renderer did. `render_site_package` round-trips method code through `ast.unparse`, which
normalizes string literals to single quotes, turning a portable `f"{p['lon']}"` into a 3.12-only
`f'{p['lon']}'`. Nothing the agent does can prevent that, and **the scripted pipeline has the
same defect**. `make_portable` repairs it after rendering, and only when the rewrite parses to
an identical AST. There is no check on the agent's own code, because the check never fired.

## Swapping the harness

The driver only calls `AgentRunner.run_episode`. `WebwrightRunner` uses webwright's
`DefaultAgent` on the `local_workspace` environment — a plain bash sandbox; no browser is
involved anywhere in this pipeline. Running these episodes under SWE-agent/mini-swe-agent instead
means adding one class in `runner.py`; no command, prompt, validator, or driver code changes.

## Verified

`pytest tests/skill_agent` — the integration test drives the entire procedure through the real
commands with a scripted agent, using the artifacts the scripted build's LLM calls actually
produced for Map, and asserts the result reproduces that library's `package_sha256` exactly.
The `verify` tests cover the safety properties: a missing extraction is an error rather than a
silent pass, a broken extraction is never composed over, and an episode that verifies nothing
leaves the library untouched.

## Scope

Build side only: gold workflows → site package. The consumer side (scratch-first plan, metadata
routing, local patches — `audited_primitive_retrieve.py`) is untouched and still runs scripted.
