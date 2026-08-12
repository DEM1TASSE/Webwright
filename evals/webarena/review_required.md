# Human review log

No blocking review items currently.

## Retrieve-only split correction

Before formal evaluation, semantic validation found that the original evaluator-only filter had
admitted one TRAIN and seven T2 state-changing/unavailable-action tasks. They were excluded and
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
