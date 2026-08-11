# Cross-Task Primitive Human Review Queue

Human review does not block the MVP implementation or unrelated experiments.

## Open

1. **Oracle provenance strength**
   - `map/search_place` is grounded in the successful task 248 workflow.
   - `map/route_between` is manually curated from the site UI contract but does not yet have two
     gold-admitted source templates.
   - Treat both as oracle pilot material only. Do not promote them as learned catalog entries
     until the updater sees two distinct gold-admitted source templates.

2. **Remote WebArena reset**
   - The reset attempt encountered a stopped GitLab container/name conflict; Shopping and Forum
     timed out during health checks.
   - No action is needed for the non-mutating Map pilot. Repair before expanding evaluation to
     those sites.

3. **Primitive usage signal**
   - Provenance markers reliably distinguish retrieved vs marker-preserved code.
   - AST similarity and execution-reached instrumentation remain stronger release features; MVP
   results must not label marker presence as proof of execution.

4. **Oracle pilot is inconclusive**
   - Accuracy changed from 6/12 to 7/12, with 2 Wins and 1 Loss.
   - Both Wins are template 68; the required second benefiting template was not observed.
   - Before promotion, review the `route_between` duration-unit example: task 152 became a Loss
     (`00:04:11` scratch correct vs `00:00:04` oracle incorrect).
   - Keep automatic catalog growth off pending a revised representation or a pre-registered
   follow-up split.

5. **Generated updater format stability**
   - With exactly two GitLab source templates, the first proposal incorrectly claimed that one
     peer was insufficient; clarifying that `new + one peer = two templates` fixed the decision.
   - The next proposal emitted JavaScript for a Python catalog and was correctly rejected by the
     static gate. An explicit Python-module constraint produced an admitted retry.
   - Shopping Admin first returned a naked function schema rather than `{"operations": [...]}`;
     the stochastic retry produced a valid admitted ADD.
   - These are updater reliability observations, not grounds for hand-editing primitives.

6. **Train-only semantic failures**
   - Shopping task384 routed incorporated the generated review parser but repeated the known
     subjective “quality” over-inclusion and scored 0.
   - GitLab task135 scratch and routed both returned `[1, 0]` and scored 0; routed used 11 steps
     versus scratch 16. The primitive changed cost but not the incorrect semantic result.
   - Keep both cases in train diagnostics. Neither task is part of the frozen test set.

7. **Formal test Loss is not attributable to primitive injection**
   - GitLab task293 is the only paired Loss.
   - Routing chose `skip`, so no workflow or primitive hint was injected. The routed answer omitted
     the `ssh://` prefix while scratch included it.
   - Count the Loss in the formal number, but do not use it as evidence that primitive content
     degraded the answer. A larger paired sample or repeated-seed analysis is needed to separate
     routing-prompt effects from ordinary run variance.

8. **Shopping Admin task1 bounded incomplete pair**
   - Neither scratch nor routed emitted a complete benchmark artifact in the original run or its
     single bounded retry. Both count as failures in the 12-task denominator.
   - Some attempts contained gateway/connect errors. The routed decision was `skip`, so this pair
     provides no positive or negative primitive-utility evidence.
   - Retry investigation exposed and fixed a harness cleanup bug: timeout now kills the complete
     subprocess group.

9. **32/24 result: accuracy tie, attribution remains mixed**
   - Scratch and routed both score 10/24, with 3 Wins and 3 Losses.
   - Workflow adaptation is outcome-sensitive: 2 Wins and 3 Losses over 13 pairs. Review the five
     changed-outcome workflows before changing the updater or retrieval prompt.
   - Primitive adaptation occurred on three Map pairs; all were both-wrong. This is neither a Win
     nor a Loss, but supplies no primitive-effectiveness evidence.
   - One additional Win occurred after `skip`, so it must not be attributed to library content.
   - Routed agent steps fell by 24.9%, but router LLM tokens and latency are not instrumented; do
     not describe this as total-cost savings without that measurement.

10. **Formal incomplete run**
    - Shopping Admin task3 scratch timed out without a complete artifact and counts as failure.
    - Routed task3 also scored incorrect, so the pair is both-wrong and does not change Win/Loss.
