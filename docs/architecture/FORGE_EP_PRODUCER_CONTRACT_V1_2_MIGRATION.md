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

For a terminal EP run, Forge additionally requires a complete positive
`execution_started_at` / `execution_completed_at` / `execution_duration_ms`
triplet from authenticated producer readback. It normalizes timestamps to UTC
and rejects unordered or duration-inconsistent values. EP 2.3.19 and newer
also bind the same triplet into newly written immutable terminal artifacts; a
partial or mismatched artifact triplet fails closed. Pre-2.3.19 immutable
artifacts legitimately lack all three fields and remain recoverable only when
the authenticated readback supplies the complete validated triplet. Forge
therefore neither fabricates timing from local receipt time nor mutates
historical EP evidence.

If a Forge release predating that completion invariant has already persisted an
`ACTIVE` Mission with every Action `COMPLETE`, proven immutable completion
bindings and a timing-less complete Host Evidence document, the installed
runtime exposes one bounded recovery: `reconcile_completed_terminal_evidence`.
It does not resume planning, derive an Action, dispatch, or alter the EP
artifact. It first performs the normal read-only preflight and then rereads the
one persisted EP dispatch. Forge accepts the result only if every non-timing
evidence field is byte-for-value identical to the persisted Host Evidence and
the EP readback supplies the complete validated timing triplet. It appends the
full evidence and performs the sole permitted `ACTIVE` → `COMPLETED`
transition. Requested, rejected and accepted outcomes are separate redacted,
immutable Forge operational events. Any different lifecycle shape, partial
timing, readback absence or identity mismatch remains fail-closed.

The persisted request's `retry_of_correlation_id` is a terminal-evidence
identity field, not display metadata. Forge accepts it only when the readback
and immutable artifact agree exactly, validates it as either null or a
non-empty correlation, and carries it into Host Evidence before Scheduler
reconciliation. A missing, substituted or malformed retry predecessor cannot
complete an Action.

The sole profile-free assurance shape is a host-verified Managed no-op:
`status`, `quality_review` and `security_review` must all be `NOT_RECORDED`,
`profile` and the findings artifact must be `null`, and the repair and open
finding counts must all be zero. Forge rejects every partial or contradictory
variant. A rejected terminal envelope is recorded as a redacted Forge
operational `ERROR` with its bounded contract `failure_code`.

`COMPLETE` requires qualified delivery and a revision. `BLOCKED` and `FAILED`
may carry null revisions. A declined unclaimed submission (`run: null`,
`NOT_STARTED`) is a non-executed terminal disposition, not fabricated host
evidence.

If EP marks an already claimed run terminal but omits its immutable terminal
artifact, Forge treats the readback as a bounded contract failure rather than
pending work. A matching `BLOCKED` or `FAILED` run/result also remains a
failure unless EP exposes its explicit, internal retry lineage in the existing
v1.2 `disposition` metadata. Forge follows that successor only when the parent
run is its exact persisted run, the successor binds that same parent with
`retry_parent_run_id`, every submission preserves the persisted Forge
correlation/provenance/producer binding, and the successor terminal artifact
passes the ordinary byte and identity checks. The result is stored as
host-proven retry resolution evidence, never as a second Forge submission or a
Forge-owned retry; Forge also appends a redacted operational audit event.
Every missing, cyclic or mismatched lineage field fails closed.

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

Forge persists the complete, already validated admission receipt in its
per-correlation binding. At terminal readback it attaches only that exact
receipt identity to the separately byte-checked terminal evidence; the receipt
is never mistaken for an execution report. Existing bindings created before
this persistence rule are recoverable only from one exact immutable
`EP_SUBMISSION_RECEIPT_RECEIVED` audit fact with matching Forge envelope,
submission, EP instance, contract versions and accepted-request digest.
Missing, duplicate or mismatched audit facts fail closed. This preserves the
causal pair of admission receipt plus terminal run/report/artifact without
copying a receipt body, prompt, credential or checkout path into Operational
Logs.

EP accepts historical v1.0 Forge provenance for existing work, but only v1.1
has the information required to create this bidirectional audit trail.  Roll
out EP first: older Forge clients ignore the additional POST response field;
the new Forge client fails closed if an EP response omits or mismatches the
versioned receipt.
