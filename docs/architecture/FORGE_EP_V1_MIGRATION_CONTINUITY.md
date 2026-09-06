# Forge / EP V1 migration continuity cross-check

**AUTHORITY = DERIVED. EP_NODE_AUTHORITY = ENGINEERING_PLATFORM.** This is a Forge readiness projection, not EP allocation authority. EP roadmap/architecture and qualification evidence decide EP sequencing.

## Consumer dependency semantics and source-pinned observation

The previous version of this projection was stale: it still described P-TRANSPORT PR #33 as open and placed the entire historical P-QUEUE/Phase-S/B8E chain in front of standalone verification. Current owner decisions and EP evidence supersede that projection.

Forge owns the consumer requirements below, not the current EP status of their
producer capabilities. For an Architect-session status report, resolve fresh
EP `origin/main` and apply the `PEER_AUTHORITY_FRESHNESS_CONTRACT` in
`ARCHITECT_SESSION.md`. This document's EP facts are an observed source
snapshot, never a locally authoritative EP status register.

**Observed EP evidence:** `origin/main=222ff52a00499f2113f1df5bdd621394c12a66c5`
at `2026-09-06T20:11:58Z`; P-NEUTRAL closure
`b44af0914622dd57c5c5c2266ee2caf9b31d9007` is its ancestor. EP's closure
register proves the same neutral platform-authority capability and the EP
roadmap/status repair is owned by EP.

Observed facts at that snapshot:

- P-TRANSPORT PR #33 is merged; P-TRANSPORT is closed.
- P-TRANSPORT provides HTTP, installed CLI and Server-owned File Inbox as three canonical submission transports normalized through Server/CENTRAL authority.
- P-NEUTRAL is a completed EP predecessor, preserving its historical and
  forensic evidence.
- P-INSTALLER-V1 is the observed EP current frontier.
- B8R project/repository identity is declared by the Canonical Project Authority Repository and validated by EP; Workspace is not required to manufacture logical project identity.
- Broader Agent separation/general dispatch/multi-host/multi-repository productization is follow-on work by default.
- `EP::STANDALONE_EP_VERIFIED` should be reached through the minimum installed one-run execution proof, not by assuming every broader future queue/Agent/B8E capability is a prerequisite.
- Any queue/lease/recovery/finalization/B8E capability that the real installed canary actually requires becomes a bounded prerequisite based on evidence.

## Consumer-gate interpretation

```text
completed:
  EP::LOCAL_CONSUMER_API_V1
  EP::P_TRANSPORT_V1
  EP::P_NEUTRAL_V1

EP-owned current frontier at the observed source snapshot:
  EP::P_INSTALLER_V1
  -> minimum installed governed execution
  -> EP::STANDALONE_EP_VERIFIED

follow-on unless proven required by the canary:
  generalized P-QUEUE policy
  broader Agent separation/dispatch
  multi-host/multi-repository execution
  remaining B8E product-parity work
  broad installed Goldens/dogfooding
```

`P_TRANSPORT_STATUS = MERGED_CLOSED`

`FORGE_OWNED_DEPENDENCY = EP installed execution/result producer`

`EP_OWNED_STATUS = RESOLVE_FRESH_EP_ORIGIN_MAIN`

`GENERAL_AGENT_SEPARATION_BLOCKS_STANDALONE = FALSE`

## Producer-to-consumer continuity

| EP producer/capability | EP-owned status | Forge consequence | Workspace consequence |
| --- | --- | --- | --- |
| Local Consumer API/auth foundation | resolve fresh from EP | consumer/auth/read foundation | consumer/auth/read foundation |
| P-TRANSPORT HTTP submission | resolve fresh from EP | canonical Forge machine submission target | future permitted-intent transport; no Workspace ownership |
| Installed one-run execution/finalization/result evidence | resolve fresh from EP | blocks first real Forge execution/reconciliation until qualified | later execution projection |
| B8R project identity/attachment runtime | resolve fresh from EP | Forge may target canonical declared repo identity | Workspace may project identity; not source of EP topology authority |
| `EP::STANDALONE_EP_VERIFIED` | resolve fresh from EP | unlocks live Forge F3/F4 canary integration | allows later installed control-plane integration |
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
