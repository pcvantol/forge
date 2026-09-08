# Forge EP producer contract v1.2 migration

Decision: `FORGE_EP_PRODUCER_CONTRACT_V1_2_MIGRATION`.

Forge is the consumer-compatibility owner. Engineering Platform (EP) owns the
producer readback and immutable terminal-evidence contracts. Forge supports
only the explicit producer-readback contract version `1.2`.

`SUPPORTED_EP_PRODUCER_READBACK_CONTRACTS = ["1.2"]`.

Before a new submission, Forge reads EP's versioned, read-only
`/v1/producer-compatibility` declaration. The declaration binds the EP
instance identity, product version, producer-readback version and terminal
evidence version. Missing, malformed, unreachable or incompatible declarations
are fail-closed: no submission, action, repair or provider mutation is made;
the execution projection remains `WAITING_EXTERNAL_CAPABILITY`.

On readback, Forge rejects every version other than `1.2` and rejects unknown
top-level fields. Terminal evidence is fetched as exact authenticated bytes,
SHA-256 checked before parsing, and cross-bound to the submission, producer,
correlation, Forge provenance, run, outcome, delivery qualification and
repository revision. A byte mismatch is
`EP_TERMINAL_EVIDENCE_DIGEST_MISMATCH`. Assurance profile, reviews, findings
artifact digest and repair rounds are bound from EP terminal evidence; Forge
does not recompute EP policy.

`COMPLETE` requires qualified delivery and a revision. `BLOCKED` and `FAILED`
may carry null revisions. A declined unclaimed submission (`run: null`,
`NOT_STARTED`) is a non-executed terminal disposition, not fabricated host
evidence.

Pinned EP producer source: `f7c08872a2d334cff097ea5f28822836e59f78c3`.
The migration is source compatibility only; it does not assert that every
installed EP instance has the declaration or runs this contract. A real Mission
canary remains separately approved work.
