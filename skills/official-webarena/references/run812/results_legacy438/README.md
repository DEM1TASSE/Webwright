# Webwright on official WebArena — retrieve + navigate

**244/438 = 55.7%** counting the 7 unscored as failures, which is the
WebArena convention. 244/431 = 56.6% over scored tasks alone.
No process errors; 5 tasks hit the 900 s cap.

## What was run

| | |
|---|---|
| tasks | 438 of 812 — every task WebArena Verified annotates as retrieve or navigate |
| agent | Webwright, gpt-5.4 via the phyagi gateway, `max_output_tokens` 16000, `step_limit` 100 |
| evaluator | official `web-arena-x/webarena@dce04686`, loaded from a pinned checkout |
| harness | `official-webarena-eval-skill` at `08fb5f8` |
| deployment | instance 2 on GCRSANDBOX410, reset before the batch |

## Results

| site | correct | |
|---|---|---|
| shopping | 57/122 | 47% |
| map | 65/108 | 60% |
| shopping_admin | 63/102 | 62% |
| gitlab | 42/69 | 61% |
| wikipedia | 9/16 | 56% |
| reddit | 7/11 | 64% |

| eval_types | correct | |
|---|---|---|
| `string_match` | 180/308 | 58% |
| `url_match` | 32/65 | 49% |
| `program_html` | 16/30 | 53% |
| `url_match+program_html` | 10/15 | 67% |
| `string_match+url_match` | 5/10 | 50% |

Per-task wall clock: median 199 s, p90 411 s, max 901 s.

## Known divergences from official WebArena

These raise or lower the number and belong beside it.

- **Judge model.** `llm_fuzzy_match` and `llm_ua_match` keep the official prompt, temperature,
  max_tokens, top_p and verdict parsing, but run on `gpt-4o`: the official
  `gpt-4-1106-preview` is not served by this gateway. Every result records both ids.
- **Step budget.** `step_limit` is 100 against the official `--max_steps` default of 30.
- **Answer and URL are self-reported.** Official reads the stop action and `page.url` from a
  live browser it owns. Webwright discards its browser, so the agent writes both into
  `final_state.json` and the evaluator reads them from there.
- **Task subset.** 438 of 812. The 374 mutate tasks need a different protocol: Webwright
  develops by re-running its script, so a mutation is applied several times per task.
- **No homepage hint.** The official prompt points the agent at a page listing site
  credentials; this prompt does not, so the agent is given less.

## Unscored

`[99, 201, 244, 286, 323, 332, 360]`

None of these is an infrastructure failure: across all ten originally-unscored tasks the runs
show zero API errors, zero format errors, a model-response count matching the step count, and
9-39 steps against a limit of 100, on sites that were healthy at the time. Five exhausted the
900-second budget and two stopped mid-progress without ever emitting a stop action, so no
answer exists to score. They are counted as failures rather than retried.

Three of the original ten (61, 81, 236) were recovered. Their agents did stop with an answer —
`exit_status: Submitted`, which is Webwright's stop action and therefore the same signal
official WebArena scores from `trajectory[-1]["answer"]` — but skipped writing
`final_state.json`. Reading the answer from the stop action instead is closer to official
semantics than discarding it, so the fallback is applied to every task rather than only to
failures; it changed nothing that already had a score, and only `string_match` tasks qualify,
since a URL or DOM cannot be reconstructed after the run. Those results carry
`"answer_source": "agent_stop_action"`. One of the three scored correct.

That two completion paths exist at all — Webwright's own stop, and this harness's artifact
spec — is the underlying problem: an agent can satisfy the first and believe it is finished.
Folding the fallback into the normal scoring path would remove the class.

## Comparison with the previous run

`../../webarena/legacy/run_401_official/` scored 59.4% over the 379 tasks both runs scored;
this run scores 55.9% on the same set. The direction matches what was changed — that run's
prompt named the task type derived from the task's own `eval_types`, discouraged answering
N/A, announced that it was a benchmark, and had the agent log itself in — but the difference
cannot be attributed to those edits:

- **The judge changed in the same batch.** `llm_fuzzy_match` and `llm_ua_match` were rewritten
  prompts on a different model in the earlier run and are the official implementations here.
  They score exactly the `fuzzy_match` and N/A tasks, so for those two categories prompt and
  scoring function moved together and neither effect can be isolated.
- **Run-to-run variance swamps the shift.** 95 of 379 tasks (25%) flipped, in both directions,
  for a net of −13. Even `must_include`, where the scoring function is unchanged deterministic
  substring matching, flipped 24 down and 8 up: the imbalance is real but a single sample of
  each configuration cannot separate it from noise.

Isolating either effect needs repeated runs of one fixed configuration to establish a variance
baseline. Until then this is an observation of the aligned configuration, not a measurement of
what alignment cost.

## Known under-count

Magento's admin grids render client-side and reach `networkidle` while still an empty skeleton
reading "0 records found", so an agent reading a count at that moment records a zero. Every
grid snapshot in this run was captured empty (94 of 94), as was every one in the earlier run
(85 of 85) — the defect predates the alignment work rather than arriving with it.

Re-running the fourteen tasks whose answers had the shape of a read-too-early result, with one
sentence added to the artifact spec, turned six of them correct: worth about 1.4 points, and
those runs are kept separately in `../webwright-gridfix-probe/` rather than folded in here,
since re-running only failures improves only what had something to gain. The fix is committed
at `1f05c15`; this baseline predates it and a comparable number would need all 438 re-run.
