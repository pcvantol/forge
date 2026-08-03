# Forge Business Workspace Architecture Authoring Report 001

## Architecture decision

The Business Workspace is a local, business-only governance boundary. It owns
Mission Candidate persistence, refinement, prioritisation, and the recorded
Business decision to approve for architecture, reject, or archive. It consumes
advisory Mission Recommendations without granting them lifecycle authority.

The implementation keeps Candidate history append-only and separates Candidate
status from Candidate maturity. It adds a non-executing Business Advisor
contract and a resolved Governance Profile policy contract, while preserving
the existing legacy profile catalog for stored Workspace compatibility.

## Exclusions

This increment introduces no Architecture Workspace, Mission Planner,
Execution Workspace, Forge Runtime, Execution Host, AI provider, forecasting,
identity system, RBAC implementation, repository operation, or automatic
Mission creation.

## Lifecycle fit

```text
Mission Recommendation → Business Workspace → Business-approved Candidate
  → Architecture Workspace → Architecture-approved Mission → Engineering
```

The Business decision is auditable and remains distinct under Solo governance
even when one identity has both Business Owner and Platform Architect roles.
