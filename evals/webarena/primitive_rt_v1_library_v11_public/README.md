# V11 public candidate library

This is the publication-safe export of the generated candidate library consumed by the V12
WebArena experiment.

- All 30 public method bodies and their method-code hashes are byte-identical to the evaluated
  local library.
- Runtime contracts, feature organization, reviews, and candidate status are preserved.
- `source_evidence` and `source_attribution` were removed from the public indexes because the raw
  audit records quote complete source workflows, including test credentials and internal deployment
  hostnames.
- The unsanitized extraction, batch, consolidation, and behavior-smoke snapshots remain local and
  are not required by runtime retrieval.
- The package is still `candidate / approved=false`; this export does not imply promotion.

Public index SHA-256:

| Site | SHA-256 |
|---|---|
| GitLab | `9016099c019793b6a1ea4286fc041cdb19506554655dfa03ea615e9529a97573` |
| Map | `ae2db761f6a5d0b564bdabe7e10567b94bd901b00b18f348a8503cb87598d40e` |
| Shopping | `540a080f2a88293e2369faeb6f945b247190925f09f5f0e4fd35d0514d53ed8e` |
| Shopping Admin | `ce930592aab933629dea34cff0bda0b2af1ebc20a5d245f17b694ab8f8043a90` |
