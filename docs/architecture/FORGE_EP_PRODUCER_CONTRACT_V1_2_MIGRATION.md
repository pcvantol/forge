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

## Bidirectional submission audit

Producer readback remains `v1.2`.  It is deliberately not widened for
submission acknowledgement: installed Forge consumers validate its root shape
exactly.  A Forge producer envelope that declares
`constraints.forge_execution.contract_version: "1.1"` instead carries two
separate facts:

- `producer.version` and `forge_application_version` are the actual Forge
  application release which materialised the envelope;
- `producer_contract_version` is the Forge Producer Contract schema version.

On a successful HTTP admission EP returns a separate `receipt` object at
receipt contract version `1.0`.  It binds the immutable EP submission ID, EP
installation and application versions, both Forge version facts, the EP
producer-readback version, and the canonical accepted-request digest.  It is
an admission acknowledgement only, never an execution receipt or execution
evidence.

Forge appends two secret-free, immutable database audit facts for every new
v1.1 exchange: `FORGE_SUBMISSION_SENT` before the request and
`EP_SUBMISSION_RECEIPT_RECEIVED` only after the receipt passes exact binding
validation.  EP appends the corresponding immutable
`FORGE_SUBMISSION_ACCEPTED` record and emits a redacted, structured central
component log.  Prompts, bearer credentials, checkout paths and receipt bodies
are not copied to either audit document or central log.

Forge also projects those two boundary facts to its append-only Operational
Logging Contract 1.0 journal as `forge_submission_sent` and
`ep_submission_receipt_received`.  The projection retains only the safe
version, product-identity, correlation and digest bindings, so the Forge and
EP operational timelines can be compared without treating Forge as the
authority for EP execution telemetry.

EP accepts historical v1.0 Forge provenance for existing work, but only v1.1
has the information required to create this bidirectional audit trail.  Roll
out EP first: older Forge clients ignore the additional POST response field;
the new Forge client fails closed if an EP response omits or mismatches the
versioned receipt.
