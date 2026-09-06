# Forge / EP V1 migration continuity cross-check

**AUTHORITY = DERIVED. EP_NODE_AUTHORITY = ENGINEERING_PLATFORM.** This is a Forge readiness projection, not EP allocation authority. EP roadmap/architecture and qualification evidence decide EP sequencing.

## Reconciled baseline — 2026-09-06

The previous version of this projection was stale: it still described P-TRANSPORT PR #33 as open and placed the entire historical P-QUEUE/Phase-S/B8E chain in front of standalone verification. Current owner decisions and EP evidence supersede that projection.

Current facts:

- P-TRANSPORT PR #33 is merged; P-TRANSPORT is closed.
- P-TRANSPORT provides HTTP, installed CLI and Server-owned File Inbox as three canonical submission transports normalized through Server/CENTRAL authority.
- P-NEUTRAL is the active EP critical-path increment.
- B8R project/repository identity is declared by the Canonical Project Authority Repository and validated by EP; Workspace is not required to manufacture logical project identity.
- Broader Agent separation/general dispatch/multi-host/multi-repository productization is follow-on work by default.
- `EP::STANDALONE_EP_VERIFIED` should be reached through the minimum installed one-run execution proof, not by assuming every broader future queue/Agent/B8E capability is a prerequisite.
- Any queue/lease/recovery/finalization/B8E capability that the real installed canary actually requires becomes a bounded prerequisite based on evidence.

## Current EP frontier

```text
completed:
  EP::LOCAL_CONSUMER_API_V1
  EP::P_TRANSPORT_V1

active:
  EP::P_NEUTRAL_V1

next critical target:
  minimum installed governed execution
  -> EP::STANDALONE_EP_VERIFIED

follow-on unless proven required by the canary:
  generalized P-QUEUE policy
  broader Agent separation/dispatch
  multi-host/multi-repository execution
  remaining B8E product-parity work
  broad installed Goldens/dogfooding
```

`P_TRANSPORT_STATUS = MERGED_CLOSED`

`CURRENT_EP_MIGRATION_FRONTIER = P_NEUTRAL`

`GENERAL_AGENT_SEPARATION_BLOCKS_STANDALONE = FALSE`

## Producer-to-consumer continuity

| EP producer/capability | Current availability | Forge consequence | Workspace consequence |
| --- | --- | --- | --- |
| Local Consumer API/auth foundation | Qualified | consumer/auth/read foundation | consumer/auth/read foundation |
| P-TRANSPORT HTTP submission | Qualified transport | canonical Forge machine submission target | future permitted-intent transport; no Workspace ownership |
| Installed one-run execution/finalization/result evidence | Qualification gap | blocks first real Forge execution/reconciliation | later execution projection |
| B8R project identity/attachment runtime | Current EP architecture | Forge may target canonical declared repo identity | Workspace may project identity; not source of EP topology authority |
| `EP::STANDALONE_EP_VERIFIED` | Next major gate | unlocks live Forge F3/F4 canary integration | allows later installed control-plane integration |
| Rich Engineering Contract Foundation | Follow-on producer hardening | long-term L0/F4 richness | quality/governance projection |
| Generalized Agent/dispatch/multi-host | Follow-on | scale/resilience, not first-canary prerequisite | later operations UX |

## Forge first executable path

After standalone verification, Forge should not wait for a new mutation transport. The intended path is:

```text
new bounded Mission
 -> immutable Action materialization
 -> execution admission
 -> persist submission key/correlation
 -> existing EP P-TRANSPORT HTTP submission
 -> EP canonical run/finalization/result evidence
 -> Forge observation/reconciliation
 -> first canary complete
```

Forge must not access EP CENTRAL directly, control launchd/Agents, scrape Console HTML or infer terminal state from logs. Ambiguous HTTP POST outcome is reconciled by canonical submission/correlation identity; no automatic duplicate POST.

## Workspace position

Workspace is not a prerequisite for the first Forge -> EP -> Forge canary. It remains owner of human/project UX and its own product state. Its onboarding/control-plane implementation may proceed contract-first but cannot become execution authority or a substitute for EP topology/admission evidence.

## Readiness classifications

| Forge capability | Current classification |
| --- | --- |
| Governance/Mission Intake/Action Derivation | QUALIFIED_BOOTSTRAP_FOUNDATION |
| Action materialization | FORGE_GAP_READY_FOR_BOUNDED_IMPLEMENTATION |
| Execution admission | FORGE_GAP_READY_FOR_BOUNDED_IMPLEMENTATION |
| EP HTTP submission transport | PRODUCER_TRANSPORT_AVAILABLE |
| EP installed execution/result producer | WAITING_EP_STANDALONE_QUALIFICATION |
| Forge EP result observation/reconciliation | CONTRACT_FIRST_PARALLEL; LIVE_COMPLETION_WAITS_EP |
| Workspace control-plane integration | NOT_FIRST_CANARY_CRITICAL_PATH |
| Autonomous next-Mission loop | WAITS_FIRST_FORGE_EP_FORGE_CANARY |

## Dependency rule

Derived planning must distinguish:

- **transport available** from **execution path qualified**;
- **minimum first-canary requirement** from **future generalized productization**;
- **producer contract gap** from **historical phase-label association**.

No Forge node may allocate EP work. No EP follow-on capability becomes a Forge blocker unless the canonical EP roadmap or actual qualification evidence says it is required.

`HIDDEN_EP_SUCCESSOR_ASSUMPTIONS = 0`

`OPAQUE_EP_V1_GATE = 0`

`WORKSPACE_ON_FIRST_CANARY_CRITICAL_PATH = FALSE`
