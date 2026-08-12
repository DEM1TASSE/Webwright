# WebArena mutate-task infrastructure

Everything needed to run and score WebArena-Verified **state-changing** tasks
(create an issue, cancel an order, change a price) with Webwright. The existing
`evals/webarena/cross_task_eval.py` only handles retrieve tasks: it hardcodes the
`{"task_type":"RETRIEVE","retrieved_data":...}` contract, rejects any task whose
evaluator set isn't `{AgentResponseEvaluator}`, and hands the evaluator a **fake
one-entry HAR** so it never actually looks at network traffic.

Mutate tasks are judged by `NetworkEventEvaluator`, which reads a real HAR. So the
missing piece was recording one.

## Why recording is not just `record_har_path`

Webwright's agent writes its own scripts, and it does not consistently use the
browser. Across the tasks we ran it reached the site three different ways:

| path | seen in | caught by |
|---|---|---|
| `urllib` | wishlist add, upvote | `http.client` patch |
| **`requests`** | create project, create issue | **`urllib3` pool patch** |
| Playwright page navigation, form submit | price edit | context `response` event |
| **`page.request.post()`** (APIRequestContext) | wishlist add via Magento `data-post` | **`pw.api` patch** |

`httpx` is patched too, for completeness -- Webwright itself uses it, though so
far only for the model gateway.

Playwright's own `record_har_path` sees only the middle row. The third row is the
subtle one: `page.request.*` does **not** emit context `request`/`response`
events, so a listener-based recorder misses it silently — we scored a correct run
`network=0.0` before catching this.

`warec/sitecustomize.py` covers all three. It is auto-imported by every Python
subprocess Webwright spawns (Webwright builds `command_env` from `os.environ`, so
`PYTHONPATH` and `WA_REC_DIR` propagate), and is a no-op unless `WA_REC_DIR` is
set. It never raises into the run.

## Trajectory vs final-run scoring

`final_script.py` gets re-run **2-5 times per task** — this happened on every
single task we observed, not occasionally. So "did the agent do X" and "does the
deliverable do X" are different questions, and one recording answers both:

```
_rec/<task>/http_*.jsonl              one raw recording
   ├─ trajectory.har   everything the agent ever did      → diagnostics
   └─ final.har        last final_runs/run_N window only  → the score
```

**Score on `final.har`.** Observed case (task 458, "reduce the price by $5"):

| final run | read price | wrote | result |
|---|---|---|---|
| run_1 | 32.00 | 27.00 | save banner missed, not persisted |
| run_2 | 32.00 | 27.00 | saved |
| run_3 | **27.00** | **22.00** | saved |

The site ended at `$22.00` for a task whose answer is `$27.00`, and the agent
reported `SUCCESS`. The trajectory window contains run_2's correct `POST` and
scores it **right**; the final-run window sees run_3's `22.00` and scores it
**wrong**. Only the second answer matches reality.

`trim_har_file` (from `webarena_verified.core.utils.trim_network_logs`) is applied
to both, which drops static assets using the evaluator's own
`NetworkEvent.is_evaluation_event` predicate — typically -89% entries — and
redacts auth headers while preserving cookies.

## Do not score the agent's self-report

`AgentResponseEvaluator` on a mutate task only checks
`{task_type, status, retrieved_data}`. Writing `SUCCESS` passes it regardless of
what the agent actually did, so it is close to free points. Meanwhile the agent's
own verdict is unreliable in **both** directions:

- task 458 reported `SUCCESS` with the site left in the wrong state;
- task 458's run_1 reported `FAILURE` while its state check had passed, because it
  demanded a success banner it failed to capture (`success_seen and final_value ==
  new_value`);
- task 470 ("cancel order 302") cancelled the order, then could not re-verify —
  the Cancel control was gone — and burned 32 steps into a timeout without ever
  writing a response.

`NetworkEventEvaluator` is the only signal that tracks what happened.

## Which tasks are safe to run without a reset

`classify_mutate_tasks.py` splits the dataset and rates repeat-safety:

```
812 tasks: mutate=356, retrieve=324, navigate=132

repeat risk            templates  tasks  effect when the write runs twice
unique-name-create            11     61  409 / name taken; end state still correct
duplicate-add                 13     59  duplicate row, or a no-op read as failure
relative-change                3     17  ACCUMULATES silently
one-shot-transition            2      9  precondition consumed; agent stalls
safe                          46    210  harmless

not idempotent: 146/356 (41%)
```

Only **relative-change** (templates 27, 247, 742 — 17 tasks) corrupts state
silently; the rest are loud or harmless. Agents write "already present, skip"
guards on their own, which is why unique-name creation survives 9 consecutive
409s and still lands the right end state. What they cannot guard is a script whose
own logic reads current state and applies a delta — re-running is correct in
isolation and wrong in aggregate.

Exclude templates 27/247/742, plus the 8 `should_not_exist` and 5
`last_event_only` tasks, and the rest can be batched without a per-task reset.

## Resetting

WebArena-Verified's `env-ctrl` has **no reset** — its ops are `init / start / stop
/ restart / get_health / cleanup`, and `_init` only sets base URLs and flushes
caches. The `POST /reset` in the docs is stale.

The real reset is cheaper than that suggests: `shopping`, `shopping_admin`,
`gitlab` and `reddit` mount **no volumes** in `docker-compose.yml` — their data is
baked into the image, so `docker rm -f` + `docker run` is a complete restore. Map,
the one site with ten volumes and a 60 GB data download, has **zero** mutate
tasks.

## Usage

```bash
export WA_CONFIG=/path/to/verified_config.json
export WA_MODEL_CONFIG=/path/to/model_gateway_54.yaml
export WA_EVAL_PYTHON=/path/to/.venv-eval/bin/python   # has webarena_verified
export WA_PYTHON=/path/to/webwright/.venv/bin/python

# tasks.json: [{"task_id":467,"tpl":186,"cat":"wishlist","sites":["shopping"],
#               "intent":"...","start_urls":["__SHOPPING__/..."]}]
python run_mutate_tasks.py tasks.json

python warec/to_har.py   runs_tasks/<task_dir> runs_tasks/_rec/<task>
python warec/score_har.py 467 runs_tasks/<task_dir>
```

End-to-end check on task 467 (`Add HONGJ Hawaiian Beach Outfits ... to my wish list`):

```
records=32  writes=6  final_runs=2  scoring_window=run_2
  POST 302 /wishlist/index/add/   product=85498
trajectory  network=1.0 response=1.0
final       network=1.0 response=1.0
```

Recorder, evaluator and the live wishlist all agree.

## Tests

`warec/tests/` runs each recording path against a throwaway local HTTP server, so
none of them touch a WebArena host:

```bash
WA_REC_DIR=/tmp/rec PYTHONPATH=warec python warec/tests/test_http_client.py
WA_REC_DIR=/tmp/rec PYTHONPATH=warec python warec/tests/test_playwright_context.py
WA_REC_DIR=/tmp/rec PYTHONPATH=warec python warec/tests/test_api_request_context.py
WA_REC_DIR=/tmp/rec PYTHONPATH=warec python warec/tests/test_urllib3_requests.py
```

`test_api_request_context.py` and `test_urllib3_requests.py` are the regression
tests for the two silent blind spots above.
