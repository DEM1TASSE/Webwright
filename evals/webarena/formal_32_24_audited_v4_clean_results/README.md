# Audited v4 clean paired results

This directory contains the 24-task retrieval-only paired result records for the updated
cross-template, same-website primitive pipeline.

- Clean scratch: 11/24 (45.8%).
- Updated primitive: 13/24 (54.2%).
- Paired outcomes: 3 wins, 1 loss, 10 both correct, 10 both wrong.
- Primitive-attributable changes: wins on tasks 122 and 154; loss on task 113.
- Task 3 was a `skip`-route win and is therefore treated as sampling variation.

Scratch runs were generated under an independent `/tmp` experiment root with no primitive arm.
All 24 trajectories were scanned for references to primitive retrieval files, site-library paths,
and historical result directories; no such access was observed. Only compact scored result records
are committed here, not full trajectories.

Step counts are diagnostic rather than end-to-end cost: frozen-plan and retrieval generation for
the primitive arm occur outside Webwright step accounting. On the ten both-correct pairs, scratch
averaged 7.6 steps and primitive averaged 8.0.
