# Map v5 primitive induction and T2 held-out evaluation

Date: 2026-08-14. Model: gpt-5.4. Site: Map. Evaluation unit: 10 unseen
templates / 19 retrieve tasks. The v5 library was regenerated from 17 gold-admitted TRAIN
workflows; no primitive was handwritten.

## Result

| arm | success | mean agent steps | correct-run mean steps |
|---|---:|---:|---:|
| frozen clean scratch | 14/19 (73.7%) | 17.47 | 16.07 |
| v4 primitive | 7/19 (36.8%) | 9.79 | 9.57 |
| v5 primitive | 12/19 (63.2%) | 11.68 | 10.58 |

Relative to v4, v5 flips five tasks from wrong to correct (80, 81, 218, 220, 364) and
regresses none. This isolates a real induction improvement: the same held-out tasks, evaluator,
and consumer harness were used.

Relative to frozen scratch, v5 has zero wins, two losses (8 and 33), 12 both-correct pairs, and
five both-wrong pairs. On the 12 both-correct pairs, steps fall from 15.92 to 10.58 (-33.5%);
10/12 are faster and 2/12 are slower.

## What changed in v5

The routing primitive is now:

```python
get_route(waypoints, transportation_method="driving")
```

Its public semantic enum is `driving | walking | biking`. The method hides the actual coupled
deployment mapping: ports 5000/5002/5001 with the low-level OSRM path profile remaining
`driving`. Its machine-readable guarantee is `configuration.kind=semantic_enum` with the same
three supported values. Search remains explicitly `completeness=partial` and cannot prove
absence.

The induction pipeline also gained deterministic envelope normalization, evidence-derived
workflow attribution, resumable batch snapshots, incremental reconsolidation, and a consolidation
gate that rejects overlapping same-feature/same-input primitives until they are merged or given
distinct semantic contracts.

## Behavior-level evidence

- Task 364, the original walking-profile regression, changes from v4 `1.6km` (wrong) to v5
  `1.7km` (correct) in 9 steps.
- Tasks 80 and 81 combine walking and driving legs. Both become correct with v5, in 11 and 8
  steps respectively.
- Task 218 correctly returns `null` after applying the five-minute walking threshold; v4 returned
  six hotels outside the intended result.
- Task 220 returns the two correct hotels in 8 steps; v4 included an extra hotel.

## Remaining failure boundary

The two regressions against scratch are both open-world candidate-set tasks:

- Task 8 asks for *all* international airports within 5 km. The partial geocoder returned no
  qualifying candidate and the consumer prematurely emitted `[]`; scratch correctly emitted the
  evaluator's `null`/not-found representation.
- Task 33 asks for Hilton hotels near an airport and each hotel's nearest supermarket. Partial
  search anchored the consumer on an extra hotel; scratch returned only the correct DoubleTree.

The next verifier change should therefore be narrow: when the final task requires exhaustive,
nearest, or absence semantics, `adapt` must not be justified solely by a partial primitive unless
another acquisition closes the core candidate set. This is not a general budget rule and should
not block direct point-to-point routing tasks.

## Artifacts

- Library: `evals/webarena/reuse_split_v1_primitive_library_v5/map/final_candidate/`
- Compact per-task results: `evals/webarena/reuse_split_v1_eval_results_v5/t2/primitive/map/`
- Full local trajectories were intentionally not committed.

Focused tests: 41 passed.
