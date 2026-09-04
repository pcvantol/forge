# Forge + Workspace V1 Authority and State Model

**Status:** proposed target model. Existing implementation is evidence, not authority to silently change this model.

## Authority rules

No authority is derived from a current directory, selected project, repository, or UI state. One concept has one storage authority. Read models may be replicated with source/version/correlation metadata; they are never mutation authorities.

| Entity | Canonical owner and store | Mutator / lifecycle | Retention and versioning |
| --- | --- | --- | --- |
| Project and Workspace-owned settings | Workspace Server | authorised Workspace intent; `DRAFT → ACTIVE → ARCHIVED → DELETION_PENDING → DELETED` | stable ID, optimistic version; tombstone/audit after deletion. |
| Repository topology/attachment | EP Server accepted attachment registry; repository-local EP declaration is portable input | EP registration/reconciliation; `DECLARED → ATTACHING → ATTACHED → DETACHED/CONFLICTED` | declaration schema + registration revision; never host-path authority. |
| Product Baseline / Project Contract | Forge versioned contract store (installed baseline is immutable input) | governed Forge contract change; `DRAFT → APPROVED → EFFECTIVE → SUPERSEDED/RETIRED` | immutable released versions; projects pin an effective revision. |
| Mission | Forge Runtime Database | approved Mission Intake only; immutable `ADMITTED`, terminal `CLOSED`/`CANCELLED` by governed process | append-only approval/evidence links; objective cannot mutate. |
| Roadmap / Backlog / Plan / Intent / Action | Forge Runtime Database | Forge planning within Mission; drafts may revise, accepted Action snapshot is immutable | stable IDs, parent/revision links; historical projection retained. |
| Effective DoR/DoD and Human Gate | Forge composes and snapshots; Workspace stores presentation/notification projection; EP stores execution proof | named human approves/rejects gate; no actorless transition | exact component versions, proof identities, actor/time retained. |
| Producer Submission / Run / retry / delivery evidence | EP canonical datastore | EP only; `PERSISTED → ADMITTED → RUNNING → WAITING_GATE → FINALIZING → terminal` | insert-only envelope/evidence and lineage. |
| repository governance desired/actual state | Forge owns desired policy interpretation; EP/provider owns observed actual state | governed change request; reconcile produces qualified result | policy/version + read-back evidence; exceptions expire or are renewed. |
| Quality record / knowledge observation | Forge proposal store | observer proposes; governed reviewer accepts/rejects | immutable source evidence, dedupe key, disposition; no automatic policy/certification. |
| provider configuration, host/Agent state, secrets | EP owns execution config/host state; secure-store owner owns secret material | EP/operator only | redacted health/audit, rotation/revocation; secret values never copied. |

## State and concurrency requirements

All mutation APIs require: `actor_id`, role/approval context, request ID, idempotency key, expected version where mutable, correlation ID, and command schema version. A retry returns the original accepted result for the same key and payload; reuse with different payload fails closed. Cross-store changes use a durable request/outbox plus reconciliation, never a distributed transaction or inferred UI success.

| Boundary | Required crash/retry behavior |
| --- | --- |
| Workspace → Forge planning request | Workspace persists intent/outbox; Forge accepts once or returns stable rejection; projection catches up asynchronously. |
| Forge → EP submission | Forge records intended Action snapshot and submission key before EP call; EP persists envelope before admission; either side can reconcile by correlation ID. |
| EP → Forge/Workspace evidence | EP evidence is immutable source; consumers record last processed cursor and can replay idempotently. |
| provider/repository mutation | EP owns lease, preflight, retry and cleanup; Forge/Workspace observe only. |
| gate/rejection repair | gate decision is immutable; repair is a new bounded Action/run linked to the rejected evidence. |

## Explicitly rejected duplicate authority

- A Workspace projection is not the project topology, Action lifecycle, run lifecycle, or approval authority.
- A repository declaration is not a host attachment, provider credential, project-policy store, or adoption decision.
- Forge does not store EP scheduler/Agent/telemetry state; EP does not store Mission semantics or Forge planning.
- A report, log, current checkout, browser selection, or provider response cannot overwrite an authoritative record without its owner’s reconciler and audit evidence.

