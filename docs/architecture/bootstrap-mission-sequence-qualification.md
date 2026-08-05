# Bootstrap Mission Sequence Qualification

Forge historically qualified the canonical bootstrap portfolio through its
existing execution harness:

`Approved Mission Queue → Mission Dispatcher → Mission Intake → Mission State → Mission Planner → Engineering Intent → Engineering Action → Runtime Prompt Renderer → Bootstrap Execution Host Adapter → Engineering Platform evidence → completion → Architecture Review → Mission Recommendation → Dispatcher`.

The portfolio is exactly `MISSION-0001` through `MISSION-0005`, in that FIFO
order. This historical harness remains useful regression evidence but does not
materialise bootstrap Missions into the Runtime Instance and does not govern
operational dispatch.

`forge.qualification.run_bootstrap_sequence_qualification` remains the legacy
bootstrap execution harness. It composes the real queue, dispatcher, intake,
durable state store, planner, renderer, adapter, review engine and
recommendation engine, and may load the five immutable definitions in
`missions/` to execute the approved portfolio. It is not the Generation 1
qualification entry point.

`forge.qualification.qualify_generation_one_bootstrap` is the Generation 1
completion reconciliation entry point. It accepts an existing Runtime Database
and verifies an integrity-valid, intentionally empty operational Runtime
Instance with an `IDLE` Dispatcher and empty queue. It never reads Mission
definitions, imports bootstrap history, creates operational state, constructs a
dispatcher or workspace, or resumes work.

A receipt/report pair is admissible only when the host-issued receipt identifies the host, receipt, run and issue time and the terminal report repeats the exact host, Mission, Intent/revision, Action, correlation and Runtime Prompt identities. The report also supplies execution timestamps, terminal outcome, validation references and repository observation. The adapter rejects missing or mismatched provenance before it reaches Mission State.

The Runtime Database records each Mission incrementally at completion, before
the Dispatcher may activate its successor. Each chain contains the Mission ID,
immutable activation and completion lifecycle events, the unique successful
Execution Receipt, Mission State, Architecture Review, at least one Mission
Recommendation, immutable Decision Evidence, and completion outcome. The
Runtime Database also checkpoints the FIFO portfolio and active/terminal
Dispatcher state. Completion requires this exact runtime chain and every Action
complete; persisted Mission State alone cannot make a Mission complete. There
is no JSON evidence cache, parallel-store fallback, source-file reconstruction,
or cached `YES` path.

The persisted qualification is restart-safe. Reinvocation after a completed Runtime Database qualification returns the same result without another dispatch. The controlled interruption regression stops immediately after the first completed Mission has persisted its host receipt, review, recommendation, and decision evidence, restarts the stores and adapter, and proves the remaining FIFO sequence without a duplicate first action or completion. Runtime qualification accepts a resumed portfolio only when its Runtime Database lifecycle and dispatcher sequence prove the same order, unique run correlations and terminal `IDLE` state.

The Generation 1 completion state is an `IDLE` Dispatcher awaiting the first
Business-approved Mission Candidate through the normal Business → Architecture
→ Mission lifecycle. A `YES` qualification declares Forge Generation 1
complete and Generation 2 ready. A successful qualification recommends
**Portfolio Intelligence Foundation**.
