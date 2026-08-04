# Runtime Evidence

Forge Runtime Database is the canonical operational authority for Mission
State, Architecture Reviews, Mission Recommendations, Decision Evidence,
Execution Receipts, and Planning State. `RuntimeEvidence` is the only query
and projection boundary for runtime qualification, governance reports, and the
Business and Architecture Workspace runtime views.

The evidence chain is `Mission → Mission State → Decision Evidence → Execution
Receipt → Execution Host Evidence → Execution Report`. Forge retains the
immutable execution receipt only: host identity, run identifier, Engineering
Report ID, timestamp, outcome, and correlation identity. Engineering Platform retains all Execution Host
Evidence, reports, and telemetry. Repository Truth retains architecture.

Bootstrap Qualification and Mission Qualification read Runtime Database
projections; they do not inspect repository implementation files or rebuild
execution history. Architecture Review, Mission Recommendation, and Decision
Evidence reports use the same projections. This preserves explicit ownership:
Forge owns runtime state, the Execution Host owns execution evidence, and the
repository owns architecture.
