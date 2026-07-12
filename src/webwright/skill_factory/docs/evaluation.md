# Evaluation details

[← back to the module README](../README.md)

Validated with this module (per-task records and the reproduction driver live in the
companion research repo).

- **WebArena — 10 templates × 3 domains (shopping_admin / gitlab / map), gold gate.** Per template
  3 train solves build the library, 2 held-out instances measure reuse (WITH library vs from
  scratch): held-out **70% vs 55% accuracy (+15pp), 14.7 vs 17.1 steps**; train 86% vs 76%.
  4 held-out tasks unsolvable from scratch are solved with the library; net reuse-wins 7 : 1
  regression. Largest saving: 33 steps → 10.
- **Retrieval stays reliable as the library grows:** all 20 held-out solves picked the correct
  skill from the shared library (grown to 10 skills), including telling apart two near-duplicate
  commit-counting skills.
- **Mixed-template batches evolve safely:** mixed batches add new templates, refine existing
  skills in place, and leave skills with no new traces byte-identical — zero cross-contamination;
  held-out reuse against a mixed-built library matches the per-template-built one.
- **Incremental growth:** a later batch improves the existing skill in place (keeps the working
  functions, adds robustness) rather than rewriting it.
- **Gate prevents pollution:** wrong solves (7 of 30 train) are dropped and never enter the library.
- **Real website (public GitHub, read-only):** end-to-end loop works — two repos solved from
  scratch → `update` distilled a parameterized skill → a held-out repo solved by reusing it
  (agent called `skill_use`, verdict `use`, answer correct).
- **Reuse value is task-dependent:** step savings are modest on easy tasks (query overhead ≈ the
  exploration it saves) and larger on harder tasks with more exploration to skip.
