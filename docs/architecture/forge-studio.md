# Forge Studio Governance Boundary

Forge Studio is a future presentation and orchestration surface. It consumes
Forge-owned architecture and resolved Governance Profile context; it does not
own a workflow, alter governance, or become an approval authority.

## Profile-aware presentation

When implemented, Studio must consume a versioned resolved Governance Profile
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
