# Primitive contract verifier: minimum development pilot

Date: 2026-08-14. This is a development check, not a success-rate estimate.

## What changed

- Induction must emit machine-readable acquisition guarantees and runtime acceptance checks.
- Retrieval proposals pass through one fail-closed verifier with three obligations:
  input reachability, guarantee sufficiency, and at least one closed acquisition.
- A rejected proposal becomes `skip`; no primitive code is injected.
- Direct injection limits reuse to verified local acquisitions and preserves scratch fallback.

## Offline frozen-proposal replay

`verifier_replay_final.json` rechecks ten previously routed proposals without rerunning the
agent. The final verifier accepts Shopping task 225 and Shopping Admin task 215. It rejects
Shopping task 387 because `product_id` is unreachable, and rejects all seven Map proposals
because the v4 route primitive exposes coupled endpoint/profile controls without explicit
configuration guarantees.

This replay isolates verifier behavior from router and agent sampling variance.

## Minimum E2E

| task | expected verifier action | actual route | score | steps | interpretation |
|---|---|---:|---:|---:|---|
| Map 8 | reject unsafe route contract | skip | 0 | 19 | no primitive injected; scratch sampled an incorrect empty list |
| Map 364 | reject unsafe route contract | skip | 0 | 16 | no primitive injected; scratch sampled `1.6km` instead of `1.7km` |
| Admin 215 | accept closed grid/detail acquisitions | adapt | 1 | 18 | consumer fell back and solved correctly, but incorporated no primitive code |

Historical scratch results for these three tasks were all correct at 18, 13, and 16 steps.
The two Map outcomes therefore cannot be read as primitive regressions: the verifier removed the
primitive intervention entirely, leaving ordinary agent variance. Admin 215 validates safe
fallback, not a primitive gain (`code_incorporated_primitives` is empty).

## Boundary learned from the pilot

Applicability verification belongs at retrieval time, but the facts it checks must be produced at
induction time. The next library build must regenerate primitives with explicit guarantees and
acceptance checks. Separately, primitives need an executable/reference grade: v4 Python Playwright
methods were synthesis material in an agent runtime where they could not run verbatim. A reference
primitive may guide adaptation, but only an executable-grade primitive can support execution
attribution or replay claims.

## Tests

- Focused changed surface: 38 passed.
- Entire `tests/skill_factory`: 206 passed, 1 unrelated existing failure because
  `evals/webarena/splits_18_12/manifest.json` is absent.

Large trajectories remain local under `e2e_runs/`; only compact result JSON should be committed.
