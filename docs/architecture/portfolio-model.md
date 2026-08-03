# Forge Portfolio Model

## Boundary

The Portfolio is the Business Workspace's governed view of product
opportunities, strategic alignment, prioritisation, business value, and
advisory learning. It is not a queue of executable work and does not own
engineering.

## Candidate and recommendation relationship

Mission Candidates enter the Portfolio as opportunities with a maturity from
`IDEA` through `READY_FOR_ARCHITECTURE`. Business Review may approve a
candidate for Architecture Review; only a Platform Architect can approve the
resulting Mission for engineering.

Mission Recommendations return to the Portfolio after Architecture Review of
Repository Truth and Execution Evidence. Recommendations are advisory inputs
to future Portfolio decisions. Neither a candidate nor a recommendation can
create, alter, or execute a Mission automatically.
The [Mission Recommendation Engine](mission-recommendation-engine.md) is the
only Forge component that derives these immutable advisory artefacts; the
[Business Workspace](business-workspace.md) owns every human decision about
them.

## Governance boundary

The Business Owner owns the decision to approve a Mission Candidate for
architecture. The Platform Architect owns the decision to approve a Mission
for engineering. Forge owns engineering only after the latter decision.
Detailed lifecycle and workspace responsibilities are canonical in the
[Product Model](product-model.md). The selected [Governance Profile](governance-model.md)
assigns who may make each decision and which advisors may participate; it does
not alter candidate maturity, approval stages, or the advisory nature of a
Mission Recommendation. Under Solo, one identity may hold both roles, but the
Business and Architecture approvals remain separate recorded decisions.
