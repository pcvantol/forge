# Project Hygiene V1 — scoped roadmap and documentary DAG

Increment: `PROJECT_HYGIENE_AND_REPOSITORY_RECONCILIATION_V1`.
Architecture: [Project Hygiene and Repository Reconciliation](../architecture/PROJECT_HYGIENE_AND_REPOSITORY_RECONCILIATION.md).
Parent strategic authority: [Forge Roadmap](../../knowledge/bootstrap/10_ROADMAP.md).
Machine-readable companion: [project-hygiene-v1.json](project-hygiene-v1.json).

This is a documentary capability DAG, not runtime configuration or execution
permission. On proposal branches the design is PENDING_PR; owning merges make
it canonical direction, not implemented/installed capability. All implementation,
consumer, UI and qualification nodes below remain PLANNED. Existing generic
development contracts, active programme graphs, grants and budgets are unchanged.

## Capability sequence

| Node | Owner | Deliverable and proof | Depends on | Status |
| --- | --- | --- | --- | --- |
| HY-0 | Forge / EP / Workspace / Forge Platform | Coordinated architecture, authority split and scoped roadmap | — | DOCUMENTATION_ONLY |
| HY-E | EP | Versioned bounded repository/host observations; freshness, scope, incomplete inventory and no mutation proof | HY-0 | PLANNED |
| HY-F | Forge | Project Context provenance projection, post-EA/provider delta refresh, bounded periodic/on-demand scans and durable cases without Mission allocation | HY-E | PLANNED |
| HY-S | Forge | Bounded evidence/intent reconciliation, explicit uncertainty, residual routing and no model-only deletion | HY-F | PLANNED |
| HY-C | EP | Reused finalizer safety plus typed scoped maintenance admission, conditional mutation, retention, idempotent per-target receipts and partial recovery | HY-E | PLANNED |
| HY-Q | Forge / EP | Shared fixtures and end-to-end observation -> case -> governed request -> EP receipt -> case reconciliation; race/lost-ack/ignored-file negatives | HY-F, HY-S, HY-C | PLANNED |
| HY-WC | Workspace | Role-aware health/chat/decision consumer contracts; no client/provider execution authority | HY-0 | PLANNED |
| HY-WO | Workspace | Read-only Repository Health/chat from qualified scoped observations and cases; stale/partial coverage and no implicit Mission | HY-WC, HY-F | PLANNED |
| HY-WM | Workspace | Scoped cleanup proposals, real owner gates and per-target outcome/history UI, with stale confirmation and cancel proof | HY-WO, HY-Q | PLANNED |
| HY-P | Forge Platform | Qualified composition/activation boundaries where hygiene is consumed; source-specific assessment, artifact retention and no installer cleanup bypass | HY-Q | PLANNED |

```text
HY-0 -> HY-E -> HY-F -> HY-S --+
          |        |          |
          +-> HY-C +---------->HY-Q -> HY-P
HY-0 -> HY-WC --+               |
HY-F ----------> HY-WO -------->HY-WM
                               ^
                               +--- HY-Q
```

The dependency table/JSON are the precise edge definition; arrows above are
orientation. HY-C reuses and strengthens existing own-run cleanup rather than
creating a second finalizer. Its standalone path does not require Forge semantic
analysis. HY-WO can ship read-only without HY-C/HY-Q/HY-WM; unavailable deletion
must not block useful observation. HY-Q includes the full governed cleanup
roundtrip, not just the read-only slice. HY-P qualifies only the hygiene features
actually included in a composition and does not require a Workspace client.

## Rollout and existing programme alignment

The smallest practical increment is HY-E/HY-F: deterministic observations and
read-only case/diagnostic projection. A bounded subset can be chosen as product
work in an already governed Mission/canary. That does not implement the full
scanner, semantic analyzer or destructive-maintenance capability.

Scheduled project-wide observation and semantic escalation follow actual
contract/resource readiness. Require finite per-project budgets, durable cursors,
permission/freshness-aware inventories and no second Mission/Action scheduler.
Use existing policy services and granted operation scopes as qualified; do not
require completion of the entire POL/GP management UI to use a bounded profile.

Automatic cleanup remains disabled until the relevant HY-C/HY-Q proof, scoped
policy activation, actual actor authority and retained recovery requirements
exist. Workspace or an LLM cannot manufacture those capabilities. A true product
residual follows normal approved Mission/intake; case creation itself is not
product work authorization.

This sub-DAG adds **no new predecessor** to the first serial Forge/EP autonomy
canary, wheel publication or every release. Existing EP repository safety still
applies. A concrete conflict relevant to the selected source/operation may block
that operation; unrelated old branches and optional unknown inventory do not.
No changes are made to the executable bootstrap JSON/node set or live grants.

## Closure evidence and reference scenario

Future implementation must separately record source tests, installed capability,
actual provider integration and activation. A manual branch cleanup is historical
example evidence, not HY-E/HY-Q qualification. The ep-producer-completion example
pins six intents to the selected main and preserves `.engineering`; it proves
nothing about every other branch or a future same-name ref.

Each completed node needs its owning PR/source, supported contract revisions,
positive and negative tests, scope, remaining exclusions and exact qualification
receipts. Documentation merges close HY-0 only as documentation delivery; they
leave the implementation nodes PLANNED.
