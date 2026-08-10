# Cross-template retrieve eval: 32 train / 24 test

## Protocol

- Websites: Shopping, GitLab, Shopping Admin, and Map.
- Seed: `20260807`.
- Per website: 8 randomly selected train templates and 6 randomly selected test templates.
- One randomly selected task instance per template.
- Train and test templates are disjoint; task selection did not use scratch outcomes, primitive
  overlap, or task difficulty.
- Each website has an independently built and frozen library.
- Test arms are paired `scratch` and `routed`; all incomplete runs remain in the denominator.

Of 32 train tasks, 17 passed the gold evaluator and were admitted as sources. Automatic library
construction produced 16 workflow priors and 7 active primitives. No primitive was hand-written.

## Main result

| arm | success | mean agent steps |
|---|---:|---:|
| scratch | 10/24 (41.7%) | 17.08 |
| routed | 10/24 (41.7%) | 12.83 |

Accuracy is tied: **3 Wins, 3 Losses, 7 both-correct, and 11 both-wrong**. Routed runs used 24.9%
fewer agent steps, but this does not include the extra router LLM call, so it is not a claim of
lower total token or wall-clock cost.

| site | scratch | routed | Win / Loss |
|---|---:|---:|---:|
| Shopping | 3/6 | 4/6 | 1 / 0 |
| GitLab | 3/6 | 2/6 | 1 / 2 |
| Shopping Admin | 2/6 | 3/6 | 1 / 0 |
| Map | 2/6 | 1/6 | 0 / 1 |

## Routing attribution

| route | pairs | scratch | routed | Win / Loss |
|---|---:|---:|---:|---:|
| workflow adapt | 13 | 6 | 5 | 2 / 3 |
| primitive adapt | 3 | 0 | 0 | 0 / 0 |
| primitive-stage skip | 8 | 4 | 5 | 1 / 0 |

The skip Win cannot be attributed to library material because no workflow or primitive code was
injected. The material-exposed arms therefore contain 2 attributable Wins and 3 Losses. The three
primitive-adapt pairs were all both-wrong: this run provides no positive primitive accuracy signal.
Workflow adaptation changed outcomes in both directions and is the main accuracy-sensitive path.

One scratch run (Shopping Admin task 3) timed out without a complete response and counts as a
failure. The other 47 runs were evaluator-scored. All result records use evaluator commit
`6473f72db5dcefc97b5725b59e734504edc28a21` with the null-expected-data fix.

## Artifacts

- Split manifest: `../splits_32_24/manifest.json`
- Site libraries and frozen hashes: `../site_libraries_32_24/`
- Train results: `../train_32_results/`
- Test run artifacts: `../test_24_runs/`
- Machine-readable aggregate: `summary.json`
