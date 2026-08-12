# Human review log

No blocking review items currently.

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

The workflow freeze uses commit `590beea`, the last pre-cross-template routing implementation. Its
distiller produces a complete parameterized standalone workflow and may create private helper
functions inside that file. Those helpers are not the separately retrieved v4 site primitive
package and do not violate arm isolation.
