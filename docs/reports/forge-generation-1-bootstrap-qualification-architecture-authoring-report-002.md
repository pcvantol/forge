# Forge Generation 1 Bootstrap Qualification Architecture Authoring Report 002

## Decision

Generation 1 Bootstrap Qualification is a read-only projection of the
persistent Runtime Instance. The qualifier obtains the portfolio from the
persisted dispatcher state and orders lifecycle transitions by their persisted,
global transition sequence. It does not import a dispatcher source constant or
read mission files.

## Ownership

Repository Truth owns architecture. The Runtime Instance owns Mission State,
Decision Evidence, Architecture Reviews, Mission Recommendations, receipt
references, planning state, and dispatcher state. Engineering Platform owns
Execution Evidence, reports, and telemetry. Forge stores only immutable,
host-issued receipt identity and its report, run, host, correlation, timestamp,
and outcome references.

## Consequence

Qualification fails closed when a persisted portfolio, lifecycle, evidence
chain, receipt identity, queue, dispatcher, or runtime-integrity check is
missing. The next architectural increment following a successful qualification
is **Generation 1 Completion Record**. Generation 2 remains unauthorized until
that qualification produces `YES` from real persisted host-issued evidence.
