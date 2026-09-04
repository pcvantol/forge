# Forge Studio Governance Boundary

Forge Studio is historical Forge terminology for a future presentation surface.
The separate Workspace product now owns human interaction and control surfaces;
this record retains only compatible presentation safeguards. See the canonical
[Productization Reconciliation](FORGE_PRODUCTIZATION_RECONCILIATION.md).

## Profile-aware presentation

When implemented by Workspace, the presentation surface must consume a versioned resolved Governance Profile
to determine:

- which canonical Business, Architecture, Execution, and Analytics Workspaces
  are visible to an assigned participant;
- which roles are assigned to each lifecycle approval;
- which advisors are available for the selected profile;
- whether an explicit profile shortcut changes an interaction; and
- which execution permissions may be requested or displayed.

Studio must not derive a different lifecycle for Solo, Duo, Startup, or
Enterprise. It presents the canonical lifecycle from the [Product Model](product-model.md)
and records the approvals required by its resolved profile. In particular,
Solo presents distinct Business and Architecture approvals even when the same
identity is assigned to both.

## Boundary

Studio is not an identity provider, RBAC service, workflow engine, approval
engine, execution host, or source of Mission truth. It cannot infer approval
from role assignment, convert a Mission Recommendation into a Mission, or
permit execution outside an approved Mission. These constraints preserve a
single product model as organizations scale.

The [Governance Profile Model](governance-model.md) is the canonical source for
profile semantics. Studio implementation remains deferred until a versioned
declarative Governance Profile Definition contract exists.

The [Architecture Workspace](architecture-workspace.md) owns the Architecture
Mission and its approval history; Studio may render that data but cannot refine
or approve it independently.
