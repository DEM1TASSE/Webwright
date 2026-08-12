# Mutate and navigate tasks on WebArena-Verified: what 61 runs showed

Date: 2026-08-12. Agent: Webwright, gpt-5.4 via gateway. Environment: the shared
WebArena-Verified deployment (no reset available).

Scope: whether Webwright can be evaluated on WebArena's **state-changing**
(`mutate`) and **navigation** (`navigate`) tasks at all, and if not, why. The
infrastructure built along the way is documented in [README.md](README.md); this
file is the result.

---

## Headline

| task type | judged on | scored correct | usable? |
|---|---|---:|---|
| retrieve | the answer text | (existing work) | yes -- judging is harness-neutral |
| mutate | the exact write request | **5/20** strict, 8/20 relaxed | marginal |
| navigate | the exact navigation event | **2/14** | no, as things stand |

Both low numbers are dominated by one cause, and it is not agent capability and
not the recorder:

> **WebArena's trace-based judging assumes the agent acts through a browser.
> Webwright's defining behaviour is to bypass the browser and write HTTP code.**

Retrieve tasks are immune -- they are judged on the answer, not on how it was
obtained. That difference is measurable, and it is the main result here.

---

## How harness-sensitive each judging mode is

**retrieve** -- `AgentResponseEvaluator` compares the answer to ground truth.
Nothing about the route matters. Neutral.

**mutate** -- `NetworkEventEvaluator` requires a request matching an exact URL,
method, post_data and status. The agent reaches the same end state by an
equivalent request and scores 0:

| task | expected | actual | outcome |
|---|---|---|---|
| 595 subscribe | `POST /f/space/subscribe.json` | `POST /f/space/subscribe` | 0 |
| 460 reduce price | `POST .../set/9/back/edit` `price=38.25` | `POST .../set/9/` `price=38.25` | 0 |
| 663 create issue | `POST /api/v4/projects/33/issues` 201 | `POST /root/metaseq/-/issues` 302 | 0 |

`warec/relaxed_score.py` re-matches the same expectation with the URL anchors
dropped but every post_data field still required — deterministic, no model. On
the 20-task batch: **strict 5/20 (25%), relaxed 8/20 (40%)**. The 15pp gap is
what the trace anchor costs this agent. The 12 that stay 0 under relaxation are
genuine failures — wrong values, wrong targets.

Note the mismatch points **both ways**: task 460 was too API-ish (skipped the
form's URL tail), tasks 663 and 744 too UI-ish (used the web form where the
evaluator wanted `/api/v4/`). The agent is not consistently wrong in one
direction; it just does not know which route is being graded.

**navigate** -- strictest of the three, because `NetworkEvent.is_navigation_event`
keys on **request headers**:

```python
headers.get("sec-fetch-dest") == "document" and ... or
headers.get("accept", "").startswith("text/html")
```

An agent that fetches the page with `urllib`/`requests` sends no such headers, so
its request **is not a navigation event at all** — it is filtered out before any
URL comparison happens. Of 14 navigate runs, 4 had a full recording (10–143
requests) and **zero navigation events**: the agent never opened a browser.

This is harsher than the mutate case. There a POST could still match; here the
correct page can be reached and the task still scores 0 by definition. Two of the
four (tasks 265, 737) expected an OSRM `route/v1/...` call — querying that routing
API over HTTP is a perfectly sensible solution, and it cannot score.

---

## Attribution: it is not the harness

Every zero was attributed with `warec/diagnose_har.py`, which reads the
evaluator's own `expected`/`actual` and searches the recording with a
progressively relaxed path prefix.

**mutate, 20 tasks:** 5 correct, 14 agent-side (7 WRONG_SHAPE, 4 FIELD_MISMATCH,
1 WRONG_ROUTE, rest uncategorised), **1 infrastructure** (task 610, zero records).

**navigate, 14 tasks:** 2 correct, 7 agent-side (4 FIELD_MISMATCH — reached the
page but never applied the required `query_params`; 3 WRONG_SHAPE), 4 no-navigation-event,
**1 infrastructure** (task 374, zero records).

Infrastructure accounts for 2 of 34 scored runs (~6%).

---

## Repetition: it corrupts state, it does not move scores

Webwright rewrites and re-runs `final_script.py` **1–8 times per task**, on every
task observed. The damage is not to the score:

| task | final runs | why it scored 0 | repetition the cause? |
|---|---:|---|---|
| 663 create issue | 1 | web UI, evaluator wants REST | no — ran once |
| 744 create project | 5 | route mismatch | no |
| 406 upvote | 8 | wrong post id | no |
| 460 reduce price | 7 | URL lacked `back/edit` | no — the first, correct save missed too |

What it damages is the site. Task 460, *reduce the price by 15%*, expected
`45.00 -> 38.25`:

```
45.00 -> 38.25 -> 32.51 -> 27.63 -> 23.49 -> 19.97 -> 16.97 -> 14.42
```

Seven successive cuts; **run_1 had already written `status=SUCCESS` at the correct
38.25**. Task 458 did the same twice ($32 → $27 → $22). Each run is internally
correct — read current state, apply delta, save — and wrong in aggregate.

`run_mutate_tasks.py` now stops the process as soon as `agent_response.json`
carries a terminal status, mirroring `has_complete_agent_response()` in
`cross_task_eval.py`. It fires on most tasks but not all: an agent that never
writes a response (task 470 cancelled order 302, then could not re-verify because
the Cancel control was gone, and burned 32 steps into a timeout) has no trigger.

`classify_mutate_tasks.py` rates the dataset: 146/356 mutate tasks are not
idempotent, but only the 17 **relative-change** tasks (templates 27, 247, 742)
corrupt state silently. Agents write their own "already present, skip" guards,
which is why unique-name creation survives repeated 409s with the right end
state. What they cannot guard against is a script whose own logic reads current
state and applies a delta.

---

## Do not score the agent's self-report

On the 20-task mutate batch, self-report and network agreed on 8 of 18 scorable
runs — **56% disagreement**:

| | network=1 | network=0 |
|---|---:|---:|
| self=SUCCESS | 4 | 9 |
| self=FAILURE | 1 | 4 |

`AgentResponseEvaluator` on a mutate task only checks
`{task_type, status, retrieved_data}` — writing `SUCCESS` passes it regardless of
what happened. Task 460 self-reported *"Reduced product price from 16.97 to
14.42"* as SUCCESS. Task 516 self-reported FAILURE and had scored 1.0.

For a reuse study this is disqualifying in a specific way: if a skill makes the
agent more confident, self-reported success rises without capability changing.

An LLM judge is worse, not better. WebArena-Verified removed LLM judging
deliberately (`docs/evaluation/removing_llm_based_evaluation.md`) in favour of
making intents verifiable. Published comparisons put LLM-judged success at 86–90%
where programmatic checks give 40–47% on the same tasks, and AgentRewardBench
finds judges systematically over-credit failed trajectories. WebArena's own
`fuzzy_match` interpolates agent output into the judge prompt unescaped, so it is
also injectable.

---

## Four recorder blind spots, each found only by running

Every one of these was silent — nothing raised, nothing logged.

| # | blind spot | symptom | found by |
|---|---|---|---|
| 1 | `page.request.*` (APIRequestContext) does not emit context `response` events | one write missing; a correct run scored 0.0 | mutate |
| 2 | urllib3 v2 overrides `HTTPConnection.request`/`getresponse`, so the `http.client` patch never fires for `requests` | four runs recorded **nothing** | mutate |
| 3 | the httpx hook also captured the model gateway | 107/167 entries were prompts carrying an API key | mutate |
| 4 | `request.headers` omits browser-added headers; `all_headers()` is needed | **every** navigate task scored 0 | navigate |

Blind spots 2 and 4 both looked like "the recorder failed to load". Playwright's
own `record_har_path` would have caught only the browser rows — one of four
transports this agent actually used.

---

## What this means for the reuse study

1. **Use retrieve tasks.** Judging is harness-neutral, the existing
   `cross_task_eval.py` handles them, and the published 55% → 70% result is
   already on retrieve.
2. **Mutate and navigate are deferred for a stated reason**, not for lack of
   effort: their judging criteria are harness-sensitive by construction, and the
   measured understatement (15pp on mutate, categorical on navigate) is larger
   than the effect a reuse experiment is trying to detect.
3. **The harness-sensitivity result stands on its own.** It is a concrete
   demonstration that cross-harness comparison on WebArena is unsound — the same
   task and the same criterion score differently depending only on whether the
   agent clicks or constructs a request. That is worth reporting.

---

## Not established

- The trajectory and final-run scoring windows have been observed to disagree
  exactly once (task 533: trajectory 1.0, final 0.0). The argument for scoring on
  the final run rests mostly on recorded price sequences, not on repeated
  disagreement.
- Task 610 and task 374 recorded nothing at all and were not root-caused.
- Relaxed scoring was run on the mutate batch only, not on navigate.
- No task was verified against live site state except task 467 (wishlist), which
  agreed with both the recorder and the evaluator.
