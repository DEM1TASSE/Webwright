---
name: official-webarena
description: Run, inspect, and score tasks from the original WebArena benchmark with Webwright and the pinned official WebArena evaluator. Use when an agent needs the original task intent/start URL/evaluator configuration, a reproducible Webwright run, or official WebArena scoring from a saved final browser state. Do not use WebArena Verified task text or evaluators in this workflow.
---

# Official WebArena

Use the original WebArena task config for all three stages: task loading, execution, and evaluation. WebArena Verified may be used by a separate experiment to define template splits, but never substitute its intent or evaluator here.

## Required inputs

Resolve these paths before running anything:

- `WEBARENA_ROOT`: official `web-arena-x/webarena` checkout pinned to commit `dce04686a56253aefba7b18a4fa0937cf1dc987b`.
- `TASKS`: normally `$WEBARENA_ROOT/config_files/test.raw.json`.
- `DEPLOYMENT`: a local JSON file mapping official placeholders to deployment URLs and optional credentials.
- one or more Webwright config specs, such as `base.yaml` and a model config.

Never commit deployment configs, credentials, generated runs, or browser state. Read [references/protocol.md](references/protocol.md) before changing evaluator behavior or final-state capture.

## Workflow

Run commands from the Webwright repository root.

### 1. Inspect the exact official task

```bash
python skills/official-webarena/scripts/official_webarena.py inspect \
  --task-id 42 \
  --webarena-root "$WEBARENA_ROOT" \
  --deployment-config "$DEPLOYMENT"
```

Check the printed `task_source`, intent, resolved start URL, sites, and official evaluator types. The command never prints credential values.

### 2. Run Webwright

```bash
python skills/official-webarena/scripts/official_webarena.py run \
  --task-id 42 \
  --webarena-root "$WEBARENA_ROOT" \
  --deployment-config "$DEPLOYMENT" \
  --output-dir outputs/official-webarena \
  --config base.yaml \
  --config model_openai.yaml
```

The runner uses the original intent, resolves official URL placeholders, and asks Webwright to save `final_state.html` and `final_state.json` before closing the live page. It automatically uses the repository's `.venv/bin/python` when present; otherwise pass `--python`. Once the final state parses and its saved DOM is present, the runner stops any trailing reflection and proceeds to evaluation. Treat a missing final state as an incomplete run, not a zero from the evaluator.

When the task carries a `storage_state`, the prompt names the resolved auth file and requires every browser context to load it unconditionally. The agent never sees a credential and spends no step logging in, matching how official WebArena, ASI and SkillWeaver all start their agents; naming the file rather than injecting it invisibly also keeps `final_script.py` runnable outside this harness. Regenerate the auth files with the official `browser_env/auto_login.py` after any site reset — a reset drops the server-side sessions, and a stale file fails as an element-not-found timeout rather than an auth error.

### 3. Evaluate the saved state

```bash
python skills/official-webarena/scripts/official_webarena.py evaluate \
  --task-id 42 \
  --run-dir outputs/official-webarena/official_webarena_task42_<timestamp> \
  --webarena-root "$WEBARENA_ROOT" \
  --deployment-config "$DEPLOYMENT"
```

For evaluator configs that use an LLM fuzzy matcher, also pass `--model-config <yaml>`. The evaluator writes `official_webarena_eval.json` into the run directory unless `--output` is supplied.

### 4. Run and evaluate together

```bash
python skills/official-webarena/scripts/official_webarena.py pipeline \
  --task-id 42 \
  --webarena-root "$WEBARENA_ROOT" \
  --deployment-config "$DEPLOYMENT" \
  --output-dir outputs/official-webarena \
  --config base.yaml \
  --config model_openai.yaml \
  --model-config model_openai.yaml
```

Use `--timeout` to bound the agent subprocess. A timeout still reports the discovered run directory but does not score unless a valid final state exists.

## Completion checks

Before reporting a result, verify all of the following:

- `task_source` is `official_webarena`.
- `official_webarena_commit` in the score is the pinned commit.
- The run directory contains both required output artifacts.
- `final_state.json.final_url` and its DOM came from the same live page.
- `status` is `scored_correct` or `scored_incorrect`; `invalid_final_state` and `unsupported_saved_state` are infrastructure outcomes, not benchmark failures.
- The result records the original task ID and official evaluator types.

Do not replace official scoring with WebArena Verified, HAR-based evaluation, string heuristics, or manual judgment.
