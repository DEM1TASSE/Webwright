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
browser. Across the tasks we ran it reached the site four different ways:

| path | seen in | caught by |
|---|---|---|
| `urllib` | wishlist add, upvote | `http.client` patch |
| **`requests`** | create project, create issue | **`urllib3` pool patch** |
| Playwright page navigation, form submit | price edit | context `response` event |
| **`page.request.post()`** (APIRequestContext) | wishlist add via Magento `data-post` | **`pw.api` patch** |

`httpx` is patched too, for completeness -- Webwright itself uses it, though so
far only for the model gateway.

Playwright's own `record_har_path` sees only the browser rows. Two of the others
fail silently and were each found only by running: `page.request.*` does **not**
emit context `request`/`response` events, so a listener-based recorder misses it — we scored a correct run
`network=0.0` before catching this. And urllib3 v2 **overrides**
`HTTPConnection.request` and `getresponse`, so patching `http.client` never fires
for `requests` -- four runs recorded literally nothing, which looked like the
recorder failing to load rather than a gap. Both have regression tests.

`warec/sitecustomize.py` covers all four. It is auto-imported by every Python
subprocess Webwright spawns (Webwright builds `command_env` from `os.environ`, so
`PYTHONPATH` and `WA_REC_DIR` propagate), and is a no-op unless `WA_REC_DIR` is
set. It never raises into the run.

## Stop the run when the agent answers

Webwright keeps rewriting and re-running `final_script.py` after it has already
produced an answer -- 1 to 8 times across the tasks we ran. For most task shapes
this is harmless. For a task that reads current state and applies a delta it is
not, because each run is independently "correct":

task 460, *reduce the price by 15%*, expected `45.00 -> 38.25`:

```
45.00 -> 38.25 -> 32.51 -> 27.63 -> 23.49 -> 19.97 -> 16.97 -> 14.42
```

Seven successive 15% cuts. **run_1 had already written `status=SUCCESS` at the
correct 38.25.** Task 458 ("reduce by $5") did the same thing twice, ending at
$22.00 for an expected $27.00.

`run_mutate_tasks.py` therefore stops the process as soon as `agent_response.json`
holds a terminal MUTATE status, mirroring `has_complete_agent_response()` in
`cross_task_eval.py`. That is the mitigation: not a smarter scoring window, but
not letting the extra runs happen.

## Which HAR window to score

One recording, two views:

```
_rec/<task>/http_*.jsonl              one raw recording
   ├─ trajectory.har   everything the agent ever did      → diagnostics
   └─ final.har        last final_runs/run_N window only  → the score
```

`final.har` is the default because it judges the deliverable rather than
something the agent stumbled into while exploring. **But neither window is
universally right, and this is worth knowing before relying on it:** when the
agent improves across reruns the last window is correct, and when it corrupts
across reruns (task 460) the *first* is. With early-stop in place first and last
coincide, which is the real reason the ambiguity stops mattering.

We have not yet observed the two windows disagreeing on an actual score. The
argument above rests on the recorded price sequences, not on two differing
evaluator outputs.

`trim_har_file` (from `webarena_verified.core.utils.trim_network_logs`) is applied
to both, which drops static assets using the evaluator's own
`NetworkEvent.is_evaluation_event` predicate and redacts auth headers while
preserving cookies.

## Repetition damages state, not scores

Attributing every failure we scored:

| task | final runs | why it scored 0 | repetition the cause? |
|---|---|---|---|
| 663 create issue | 1 | posted to the web UI; evaluator wants `POST /api/v4/.../issues` 201 | no -- ran once |
| 744 create project | 5 | same, plus `401` on `/api/v4/projects/196/members` -- session cookie, no API token | no -- capability gap |
| 406 upvote | 8 | voted 134852/134851, expected 119517 | no -- wrong target |
| 460 reduce price | 7 | URL lacked the `back/edit` suffix the regex anchors on | no -- the first, correct save missed too |
| 472 cancel order | 2 | scored **1.0** | -- |

None of the zeros come from repetition. What repetition does instead is corrupt
the site silently (460, 458 -- both relative-change) and stall one-shot tasks:
task 470 cancelled order 302 on its first execution, then could not re-verify
because the Cancel control was gone, and burned 32 steps into a timeout without
writing any answer.

**A separate, larger problem for GitLab:** its mutate tasks expect REST API calls
(`POST /api/v4/projects`, `201`), while the agent drives the web UI and only holds
a session cookie. Task 663 failed this way on a single run. This depresses GitLab
mutate scores independently of anything in this harness.

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
