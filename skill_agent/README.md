# skill_agent — the audited build pipeline, run by a terminal agent

The scripted pipeline (`webwright.skill_factory.audited_primitive_build`) builds a site primitive
library by calling `llm_json` once per stage and feeding validator errors back into the next
prompt. The model never sees the source workflow as a file, never runs the validator, and gets at
most `max_attempts` blind retries.

This package runs the same pipeline as a sequence of terminal-agent episodes. The agent gets a
bash workspace, the real source scripts on disk, and the validator as a command it runs itself.

The validators, batching, apply/consolidate logic, and output layout are imported unchanged, so
an agentic library and a scripted library are directly diffable.

## What actually changed

| | scripted | agentic |
|---|---|---|
| Sees the source workflow | as a JSON string in the prompt | as `in/sources/<id>.py`, greppable, parseable, runnable |
| Validator feedback | injected into the next prompt | a command the agent runs as often as it likes |
| Retries | up to `max_attempts` whole-stage regenerations | in-episode iteration, plus stage retries as a backstop |
| Emitting a primitive | one giant JSON with Python escaped inside a string | one file per operation + real `.py` method bodies |
| Quality gate | second `llm_json` call in the same driver loop | its own episode with a fresh context |

The last row of the middle column is a real constraint, not a stylistic one: a site proposal with
several primitives' full method bodies does not fit in one model response. `skill_agent.assemble`
composes `out/proposal.json` from small per-operation files so a stage is never one oversized
generation.

## Stages

Each stage is one episode with the same on-disk contract:

```
<workspace>/in/context.json     staged inputs (read-only by convention)
<workspace>/in/sources/*.py     gold final_script.py behind each workflow
<workspace>/in/code/*.py        pooled/proposed method bodies, as real Python
<workspace>/out/<artifact>      the one JSON file the agent must produce
```

| stage | per | artifact | validator |
|---|---|---|---|
| `extract` | workflow | `out/extraction.json` | `validate_extraction` |
| `build` | batch | `out/proposal.json` | `validate_build_proposal` |
| `quality` | batch | `out/verdicts.json` | `validate_quality_verdicts` |
| `consolidate` | site | `out/proposal.json` | `validate_consolidation` |

Commands available to the agent inside a workspace:

```bash
python -m skill_agent.assemble build        # out/ops/*.json + out/code/*.py -> out/proposal.json
python -m skill_agent.check build           # exit 0 = accepted; otherwise every error, in full
```

Stage prompts live in `prompts/*.md` and carry the boundary rules from the scripted system
prompts (`_EXTRACT_SYS`, `_BUILD_SYS`, `_QUALITY_SYS`, `_CONSOLIDATE_SYS`) verbatim in substance.

## Running it

```bash
set -a && . /path/to/webwright/.env && set +a      # OPENAI_API_KEY for the gateway

PYTHONPATH=src:. python -m skill_agent.build \
    --workflows skill_agent/inputs/workflows \
    --output runs/agentic_v1 \
    --model-config /path/to/model_gateway_54.yaml \
    --sites map
```

Resumable: a stage whose `validation.json` already reports accepted is skipped on re-run.

## Inputs are frozen

The scripted build resolved its sources at build time from a manifest of result JSONs pointing at
untracked `<run_dir>/final_script.py` files, so a build only reproduced on the machine that
produced those runs. `skill_agent/inputs/workflows/<site>.json` is a self-contained snapshot —
code inlined, `MANIFEST.json` recording each source's `record_path` and code SHA256.

The current snapshot is the same 17 gold-admitted workflows behind `audited_site_library_v2`:
GitLab 7, Shopping 4, Map 3, Shopping Admin 3. Re-freeze with:

```bash
python -m skill_agent.tools.snapshot_inputs --from-library <library_dir> --output skill_agent/inputs
python -m skill_agent.tools.snapshot_inputs --manifest m.json --dataset d.json --output skill_agent/inputs
```

## Output

Identical layout to the scripted build — `config.json`, `workflow_order.json`, `extractions/`,
`batches/batch_NNN/{proposal,validation,primitive_diff,snapshot}`, `pre_consolidation/`,
`consolidation/{proposal,coverage}`, `final_candidate/{package.py,index.json,review.md}`,
`audit.json` — plus `agent_runs/` holding every episode workspace and `trajectory.json`, so each
primitive traces back to the commands that produced it.

## Swapping the harness

The driver only calls `AgentRunner.run_episode`. `WebwrightRunner` uses webwright's `DefaultAgent`
on the `local_workspace` environment — a plain bash sandbox; no browser is involved anywhere in
this pipeline. Running these stages under SWE-agent/mini-swe-agent instead means adding one class
in `runner.py`; no stage, prompt, validator, or driver code changes.

## Verified

`pytest tests/skill_agent` — the replay test drives the whole pipeline with the artifacts the
scripted build's LLM calls actually produced for Map, and asserts the driver reproduces that
library's `package_sha256` exactly. If it fails, the port changed pipeline semantics.

## Scope

Build side only: gold workflows → site package. The consumer side (scratch-first plan,
metadata routing, local patches — `audited_primitive_retrieve.py`) is untouched and still runs
scripted.
