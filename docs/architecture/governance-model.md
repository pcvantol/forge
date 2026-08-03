# Forge Governance Profile Model

## Purpose and invariant

The Governance Profile is Forge's canonical scaling mechanism. It defines who
participates in governance; it never defines a different engineering workflow.
Every profile uses the same product lifecycle:

```text
Vision → Portfolio → Mission Candidate → Business Review →
Approved for Architecture → Architecture Review →
Approved for Engineering → Mission → Engineering → Execution → Evidence →
Architecture Review → Mission Recommendation → Portfolio
```

A profile changes role assignment, approval authority, workspace visibility,
advisor availability, execution permissions, and any explicitly declared
approval shortcut. It does not change the lifecycle, Engineering model,
Mission model, or Portfolio model. A shortcut can reduce an interaction only
when declared; it cannot omit a lifecycle stage or an auditable approval.

## Profile definition

The versioned declarative Governance Profile Definition resolves a Workspace
selection into:

- participating roles and their assignments;
- an approval matrix for Mission Candidates, Architecture, Engineering,
  Execution, and Mission Recommendations;
- available Business, Architecture, Execution, Security, Legal, and Portfolio
  Advisors;
- visibility of the canonical Business, Architecture, Execution, and Analytics
  Workspaces;
- execution permissions; and
- explicit, bounded approval shortcuts.

It is a policy input, not an identity provider, RBAC system, workflow engine,
queue, or authorization implementation. A future Workspace implementation
consumes the resolved profile to present the applicable people, workspaces,
advisors, and approval requirements while preserving the invariant lifecycle.

## Canonical profiles

| Profile | Role assignment | Governance consequence |
| --- | --- | --- |
| Solo | One identity is both Business Owner and Platform Architect; Forge performs Engineering. | Business and Architecture Workspaces remain distinct. The shared identity records both approvals separately. |
| Duo | Business Owner and Platform Architect are separate identities; Forge performs Engineering. | Responsibility is separated without adding or removing lifecycle stages. |
| Startup | Business, Architecture, and Engineering Lead participate before Forge. | Additional review or approval responsibilities may be declared, but remain optional policy rather than new workflow stages. |
| Enterprise | Portfolio, Business, Architecture, Security, Compliance, and Forge participate. | Security and Compliance availability and approval authority are declared by profile; Execution remains unchanged. |

### Solo is responsibility composition, not a separate operating mode

Solo does not skip governance. It combines Business Owner and Platform
Architect responsibility in one assigned identity. Business approval still
exists; Architecture approval still exists; each is recorded against its
canonical lifecycle stage. This retains auditability, rationale, portfolio
history, and a direct path to later separation of duties.

## Scaling without model forks

A Workspace created under Solo migrates to Duo, Startup, or Enterprise by
changing its Governance Profile and role assignments. Mission identity,
Mission history, Portfolio records, workspace boundaries, and the engineering
workflow remain intact; no Mission migration is required. This avoids distinct
"single-user" and "enterprise" implementations while allowing governance to
become more specific as an organization grows.

## Compatibility and resolved profiles

The 0.2 persisted `governance_profile` schema remains a bootstrap compatibility
catalog (`solo`, `two_person`, `team`, `enterprise`). The Business Workspace
implements the versioned resolved Governance Profile contract with canonical
`solo`, `duo`, `startup`, and `enterprise` vocabulary. Existing `two_person`
and `team` values are accepted only with an explicit compatibility note that
records their resolution to Duo and Startup; stored data is not silently
rewritten or reinterpreted.

Engineering Mode and Governance Profile remain independent: an Engineering
Mode describes execution context, while a Governance Profile describes who may
participate and approve in that context. Neither selection grants runtime
authority by itself.

## References and next increment

The [Product Model](product-model.md) owns the invariant lifecycle. The
[Portfolio Model](portfolio-model.md), [Workspace Model](workspace-foundation.md),
[Mission architecture](engineering-mission.md), and [Forge Studio model](forge-studio.md)
apply this profile boundary in their domains.

The [Business Workspace](business-workspace.md) consumes the resolved profile
for business-facing governance while preserving this model's invariant. The
recommended next increment is **Architecture Workspace**. It receives only
Business-approved Mission Candidates and prepares them for the distinct
Architecture approval before engineering. It must not implement authentication,
RBAC, workflow automation, or separate operating modes.
