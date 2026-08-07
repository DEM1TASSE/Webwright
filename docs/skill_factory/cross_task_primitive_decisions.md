# Cross-Task Primitive Decisions

1. Workflows remain complete template-level standalone programs.
2. MVP primitives are prompt-time synthesis material copied into workflows, never runtime imports.
3. The active primitive catalog is flat and self-contained; no public DAG or version solver.
4. `requires/provides` represents browser state only and creates no code dependency.
5. The current evaluation is cross-template only: same-template workflow use remains in the
   production pipeline but is excluded from this split and its claims.
6. Cross-template routing is metadata-only workflow adapt/skip → generated primitive
   use/adapt/skip → scratch. Full code is fetched only after use/adapt.
7. The MVP does not mix workflow adaptation with primitive injection in one run.
8. Same-template evidence updates workflows; cross-template evidence may update primitives.
9. Primitive updates are triggered by a new gold-admitted template, not every task instance.
10. Human review is asynchronous: uncertain proposals are recorded and other work continues.
11. Phase 0 uses a pre-registered gate: at least 10 instances / 5 held-out templates;
   GO requires `wins - losses >= 2` with wins on at least 2 templates.
12. Mutation and `NetworkEventEvaluator` are excluded. Read-only Map tasks run without per-task
    resets; reset is reserved for demonstrated state contamination.
13. The frozen Map oracle pilot is inconclusive (`2 Wins - 1 Loss = +1`, one winning template);
    therefore no candidate is promoted and active catalog growth is held at 2 → 2.
