# Autonomous Mission Runtime Scheduler

## Ownership boundary

Forge owns Mission semantics, Living Mission Graph reconciliation, selection of
one approved Engineering Action, the Producer Submission Envelope, Execution
Context, Runtime reconciliation, and Mission completion. Engineering Platform
continues to own admission, readiness, execution, liveness, Retry/Resume, and
immutable Execution Receipts. The scheduler neither parses prompts nor reads
Forge state from Engineering Platform.

## Autonomous iteration

Before every iteration the scheduler resolves exactly one ACTIVE Mission,
rechecks Business and Architecture approval, intervention and capability
boundaries, and derives the single dependency-satisfied READY Action from the
current Living Mission Graph. It projects the canonical Execution Context and
embeds that unchanged snapshot in a complete versioned Producer Submission
Envelope. A persisted deterministic Submission ID makes repeated evaluation
and restart recovery idempotent.

Only one submission may be outstanding for a Mission. The full envelope is
persisted before it is handed to the EP-owned atomic ingress adapter. An
outstanding submission is always recovered and reconciled before another
Action can be selected.

## Receipt reconciliation and completion

Forge advances an Action only after the immutable receipt matches the stored
Submission ID, run ID, Mission, Intent, Action, integrity digest and terminal
outcome. A COMPLETE receipt records bounded lineage, updates Mission Runtime,
reconciles the graph and immediately submits the next bounded Action when it
is eligible. BLOCKED, FAILED, invalid receipt, ambiguity, governance,
capability and operator boundaries fail closed with a bounded pause reason.

Mission completion requires no ACTIVE/READY/executable Action and no active
Intent. Completion appends Decision Evidence, preserves history, produces the
final Execution Context on normal projection, and transitions Dispatcher to
IDLE. No operator "Continue Active Mission" prompt is part of this loop.
