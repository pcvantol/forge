# Forge Engineering Proposal Generator Foundation 0.6

An Engineering Proposal is a generated, governed intention. It describes what
should happen, why it matters, its bounded scope, dependencies, risks, and
evidence. It is distinct from the declarative 0.5 Engineering Increment
Proposal: the latter is planning input; the 0.6 artifact is generated output.

`EngineeringProposalGenerator` is local and deterministic. It consumes a
validated Workspace, Engineering Plan, its goals and increment proposals, and
optional knowledge evidence references. It validates that the selected
increment is ordered by the plan and linked to a goal in the same workspace. Its stable
output preserves source identities in creation metadata and carries all input
evidence without reading any referenced source.

Generation always returns `DRAFT`. Lifecycle transitions are explicit pure
operations in this order: `DRAFT`, `PROPOSED`, `APPROVED`, `EXECUTED`. A
transition records no approval decision, performs no repository operation, and
executes no work. Approval and execution behavior remain future separately
governed capabilities.
