# Human review log

No blocking review items currently.

## Formal evaluation release decision

The frozen evaluation completed with 317/317 structurally valid records. T1 exact workflow scored
42/70 versus scratch 44/70. T2 primitive-v4-direct scored 37/59 versus scratch 43/59; the
workflow-adapt ablation scored 33/59. The current recommendation is **do not promote v4 as a
release library**. Human review is requested only for the release decision; it does not block
retaining the candidate, build provenance, or formal results.

## Map contract and routing changes proposed for v5

All seven T2 primitive paired losses unique to Map selected the same `search_places + get_route`
pair. Inspection found that the route primitive exposes transport profile and service base URL as
independent knobs even though the deployment couples mode to endpoint/port. Failed consumers asked
for `foot`/`walking` on the default port and received route steps marked `driving`. In addition,
`search_places` declares `is_complete=false`, yet the router adapted it for exact-set and
NOT_FOUND-sensitive tasks while leaving core candidate discovery as a remaining gap.

Recommended v5 changes are: expose a semantic `transport_mode` and map/verify the correct endpoint
inside the primitive; add explicit candidate-set scope/completeness metadata; and reject `adapt`
when an exact-set task lacks a complete core candidate acquisition. These changes should first be
tested on the seven Map losses plus previously correct Map cases, not silently applied to the
frozen v4 result.

## Router reproducibility

The retrieval audit and E2E decisions matched on 176/188 records, while exact selected material
matched on 175/188. The audit and E2E currently resample the LLM router independently. A future
formal protocol should persist one routing manifest and consume it during E2E if route stability is
part of the claim. This is a follow-up design choice, not a reason to invalidate the completed run;
the final report uses actual E2E exposure.

## Primitive execution attribution

All 40 E2E tasks with primitive exposure contained the selected code markers in their final script,
but none produced declared usage or an execution trace. The present evidence supports
"exposed/incorporated", not "executed". A release-grade pipeline should add execution-level
instrumentation before making function-use claims.

## Retrieve-only split correction

Before formal evaluation, semantic validation found that the original evaluator-only filter had
admitted one TRAIN and eight T2 state-changing/unavailable-action tasks. They were excluded and
recorded in the split metadata. All 121 TRAIN attempts remain auditable; task 792 was incorrect and
was never gold-admitted, so neither frozen library required regeneration.

## Credential rotation

During experiment orchestration on 2026-08-12, a failed environment-forwarding command printed
the inherited `OPENAI_API_KEY` in tool output. The experiment can continue, but the credential
owner should rotate that key after the active jobs finish.

## GitLab v4 build retry

The first strict GitLab consolidation exhausted three generation attempts. The quality gate
rejected a lossy merged commit contract and the coverage gate rejected dropping two reusable
project-search acquisitions. Its complete artifacts are retained under
`reuse_split_v1_primitive_library_v4/gitlab_failed_attempt_1/`. A second generation run uses five
attempts with the same frozen v4 prompts and unchanged gates.

## Workflow grouping failure (automatically corrected)

The first workflow build reused the legacy `learn` grouping stage. Despite receiving only official
template 329 runs, that model stage split them into two skills. The artifacts are retained as
`reuse_split_v1_workflow_{library,build}_flawed_grouping/` and excluded from evaluation. The formal
builder now bypasses grouping and feeds each official `intent_template` plus its exact
`instantiation_dict` values directly to the frozen `evolve` implementation. Human review is not
required to continue, but this is evidence that inferred grouping should not override known
dataset template identities.

## Primitive-direct router correction

The first retrieval-only audit revealed that the shared audited retriever still used its
scratch-first decision prompt even when no scratch plan was supplied. This caused false skips with
the explicit reason that a scratch plan was missing, contradicting the frozen primitive-direct arm.
Those audit files are retained under `reuse_split_v1_retrieval_audit_invalid_scratch_router/` and
excluded. The formal direct arm now has a metadata-only `use/adapt/skip` prompt that explicitly does
not require a scratch plan; the scratch-first code path remains unchanged and is not used here.

The workflow freeze uses commit `590beea`, the last pre-cross-template routing implementation. Its
distiller produces a complete parameterized standalone workflow and may create private helper
functions inside that file. Those helpers are not the separately retrieved v4 site primitive
package and do not violate arm isolation.
