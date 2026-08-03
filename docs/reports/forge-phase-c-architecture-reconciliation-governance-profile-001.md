# Forge Phase C Architecture Reconciliation Report — Governance Profile Model

**Status:** Reconciled architecture

## Outcome

Governance Profiles are Forge's canonical scaling mechanism. They preserve one
canonical lifecycle by determining who performs a stage, who may approve it,
which workspaces and advisors are available, and which execution permissions
or explicit shortcuts apply. They do not redefine the lifecycle, Engineering
model, Mission model, or Portfolio model.

## Reconciliation answers

### How profiles preserve one canonical workflow

The lifecycle remains `Vision → Portfolio → Mission Candidate → Business
Review → Approved for Architecture → Architecture Review → Approved for
Engineering → Mission → Engineering → Execution → Evidence → Architecture
Review → Mission Recommendation → Portfolio`. A resolved profile applies
roles and approval authority to these existing stages only. An explicit
shortcut can change interaction cost, never remove a required stage or its
audit record.

### Why Solo is not a separate operating mode

Solo assigns one identity as both Business Owner and Platform Architect. The
Business and Architecture Workspaces remain distinct, and the shared identity
records separate Business and Architecture approvals. Solo therefore preserves
auditability, rationale, portfolio history, and later separation of duties;
it is responsibility composition rather than governance bypass.

### How Forge scales from one maintainer to enterprise

Solo, Duo, Startup, and Enterprise use the same Mission and Portfolio records,
Workspace topology, lifecycle, Forge Engineering, and Execution boundary.
Growth changes profile selection and role assignments: Duo separates Business
Owner and Platform Architect; Startup may add an Engineering Lead; Enterprise
declares Portfolio, Security, and Compliance participation. A Workspace can
move between profiles without Mission migration or architectural change.

### How role assignments differ from workflow definitions

The workflow defines stage order and invariants. Role assignments identify the
participants who may act at those stages. The approval matrix determines who
may approve Mission Candidates, Architecture, Engineering, Execution, and
Mission Recommendations. Neither assignment nor matrix can create, remove, or
reorder workflow stages.

### How future Workspaces consume the profile

Future Workspace implementations resolve a versioned declarative profile into
participating roles, assignments, approval matrix, visible canonical
workspaces, available advisors, execution permissions, and explicit shortcuts.
They must use that result as policy context while rendering or enforcing the
invariant lifecycle. They must not build distinct Solo or Enterprise workflows,
infer an approval, or let a profile selection grant authority by itself.

## Compatibility and implementation boundary

The existing 0.2 persisted values (`solo`, `two_person`, `team`, and
`enterprise`) remain legacy bootstrap catalog values. This reconciliation does
not change their storage or reinterpret existing data. The implementation must
define explicit read compatibility and migration before adopting canonical
`solo`, `duo`, `startup`, and `enterprise` profile definitions.

## Recommended next increment

Implement a versioned, declarative Governance Profile Definition contract and
resolver with compatibility handling. Its bounded fields are role assignments,
approval matrix, visible workspaces, available advisors, execution permissions,
and explicit shortcuts. Do not add authentication, RBAC, workflow automation,
Studio UI, or separate Single User or Enterprise implementations.
