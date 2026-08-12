# Human review log

No blocking review items currently.

## Credential rotation

During experiment orchestration on 2026-08-12, a failed environment-forwarding command printed
the inherited `OPENAI_API_KEY` in tool output. The experiment can continue, but the credential
owner should rotate that key after the active jobs finish.

The workflow freeze uses commit `590beea`, the last pre-cross-template routing implementation. Its
distiller produces a complete parameterized standalone workflow and may create private helper
functions inside that file. Those helpers are not the separately retrieved v4 site primitive
package and do not violate arm isolation.
