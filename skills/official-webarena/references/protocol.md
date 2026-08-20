# Original WebArena protocol

## Source of truth

This skill deliberately keeps one source of truth throughout the run:

| Stage | Source |
|---|---|
| Intent, sites, start URL | original WebArena task row |
| URL placeholders and credentials | local deployment config |
| Agent execution | Webwright |
| Gold config and evaluator types | original WebArena task row |
| Scoring implementation | pinned official WebArena `evaluator_router` |

WebArena Verified can supply external split metadata such as template clusters. If it does, join only on `task_id`; reload the execution row from original WebArena and keep the original intent and `eval` object.

## Official checkout

Use the historical checkout expected by the adapter:

```bash
git clone https://github.com/web-arena-x/webarena.git /path/to/webarena
git -C /path/to/webarena checkout dce04686a56253aefba7b18a4fa0937cf1dc987b
```

The runner defaults to `<WEBARENA_ROOT>/config_files/test.raw.json`. Override `--tasks` only when using another original WebArena config file.

## Deployment config

The file is local and must not be committed. Minimal shape:

```json
{
  "environments": {
    "__GITLAB__": {
      "urls": ["http://example.internal:8023"],
      "credentials": {"username": "...", "password": "..."}
    },
    "__MAP__": {"urls": ["http://example.internal:3000"]}
  }
}
```

Every placeholder present in a selected task must resolve to a URL. The task inspector reports unresolved placeholders and exits non-zero before starting an agent.

## Final-state contract

Webwright must create these files inside its timestamped run directory:

- `final_state.html`: exact `await page.content()` output captured before the page closes.
- `final_state.json`: `final_url`, `html_path`, integer-or-null `document_status`, and textual `answer`.
- (Removed) `agent_response.json`: no longer requested. Official scoring reads the answer from
  `final_state.json`, and the completion signal is the parsed final state itself, so the extra file
  cost the agent a write without feeding any evaluator.

The official adapter restores the saved HTML in a local Playwright page and wraps it with the recorded final URL. It then calls the pinned official `evaluator_router` with the original task config. It does not consume HAR traffic.

## Known boundary

Saved-state evaluation supports URL matching, string matching, and DOM-based `program_html` checks. A small set of official configs calls dynamic site helpers that require live backend state; the adapter returns `unsupported_saved_state` when one of those helpers is invoked. Do not convert that outcome into an incorrect benchmark score. Use a live official browser harness for those tasks.

The adapter uses optional Webwright LLM helpers only when an official string evaluator requests fuzzy or unachievable-answer matching. Pass `--model-config` in that case.

## Isolation

Give each experimental arm a distinct output root. Do not let a scratch run see primitive retrieval records, workflow code, or another arm's workspace. Reuse the same original task config and deployment assignment across paired arms.
