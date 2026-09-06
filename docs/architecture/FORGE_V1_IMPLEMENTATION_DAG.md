# Forge V1 Implementation DAG

**AUTHORITY = DERIVED.** Source authority is the canonical Forge roadmap and product-owned EP/Workspace contracts. This document never allocates EP or Workspace work.

## Current bootstrap reconciliation — 2026-09-06

```text
Forge Action-Derivation foundation (qualified)
  -> EP P-NEUTRAL closure
  -> EP P-INSTALLER-V1 server-only qualification
  -> DJConnect declaration + CENTRAL attachment
  -> first real DJConnect EP Action
  -> EP::STANDALONE_EP_VERIFIED
  -> real EP self-development Action through CENTRAL
  -> EP::SELF_HOSTED_ENGINEERING_VERIFIED
  -> Forge repository direct-EP dogfood Action
  -> Forge F3/F4 materialization/admission
  -> canonical EP P-TRANSPORT HTTP submission
  -> EP run/finalization/result evidence
  -> Forge observation/reconciliation
  -> first Forge -> EP -> Forge governed canary
  -> autonomous next-Mission loop
```

## Critical corrections

- P-TRANSPORT is merged/closed and provides HTTP, installed CLI and Server-owned File Inbox submission transports. Forge reuses HTTP.
- The earlier read-only Local Consumer API and later P-TRANSPORT HTTP mutation ingress are distinct.
- P-INSTALLER-V1 is a server-only installed-product qualification gate before real-project execution; it does not install Forge, Workspace or generalized Agent productization.
- B8R identity comes from committed `.engineering-platform/repository.json`, not Workspace/runtime/path inference.
- Workspace is not a runtime prerequisite for first standalone or Forge autonomy canaries.
- General Agent separation, generalized dispatch, multi-host scheduling and multi-repository parallel mutation are follow-on unless a real canary proves a concrete dependency.
- Broad P-QUEUE/B8E labels are not blanket blockers; only concrete execution/finalization/evidence gaps discovered by the canaries block progress.
- Real-project proofs deliberately separate execution-product qualification from Forge orchestration: DJConnect proves standalone, EP proves self-development, Forge direct dogfood proves EP can engineer Forge, then Forge orchestrates EP.

`P_TRANSPORT_STATUS = MERGED_CLOSED`
`P_INSTALLER_V1_ON_CRITICAL_PATH = TRUE`
`WORKSPACE_ON_FIRST_FORGE_AUTONOMY_CRITICAL_PATH = FALSE`
`GENERAL_AGENT_SEPARATION_ON_STANDALONE_CRITICAL_PATH = FALSE`
`P_TRANSPORT_HTTP_SUBMISSION_REUSED_BY_FORGE = TRUE`

## Capability inventory

| Capability | Current status | Disposition |
| --- | --- | --- |
| Forge governance/Mission/Action-Derivation foundation | QUALIFIED | KEEP; on hold for live execution integration. |
| EP P-TRANSPORT submission transport | AVAILABLE | Reuse HTTP; no duplicate transport. |
| EP P-NEUTRAL | ACTIVE | Current EP critical path. |
| EP P-INSTALLER-V1 | REQUIRED NEXT | Reproducible server-only installed product. |
| DJConnect real-project standalone canary | REQUIRED AFTER INSTALLER | Earns `EP::STANDALONE_EP_VERIFIED`. |
| EP self-development through CENTRAL | REQUIRED POST-STANDALONE PRODUCER PROOF | Earns `EP::SELF_HOSTED_ENGINEERING_VERIFIED`. |
| Forge direct-EP repository dogfood | REQUIRED BEFORE/DURING FORGE INTEGRATION | Proves EP can engineer Forge without Forge orchestration. |
| Forge Action materialization + execution admission | FORGE GAP | Resume after producer proofs. |
| Forge EP observation/reconciliation | FORGE GAP | Resume with live installed producer. |
| Project Intelligence architecture seams | PREPARATION | Non-blocking contracts may be stabilized early. |
| Workspace Roadmap/DAG Governance | FOLLOW-ON CORE PRODUCT | Not required for first machine loop; consumes Forge project intelligence. |
| Workspace direct EP dogfood | FOLLOW-ON | Useful but non-blocking for first Forge autonomy. |
| General Agent/dispatch/multi-host/multi-repo | EP FOLLOW-ON | Not first-canary blockers by default. |

## Critical execution DAG

```text
                         EP P-NEUTRAL
                              |
                              v
                       P-INSTALLER-V1
                              |
                              v
                  DJConnect B8R declaration
                              |
                              v
                 real DJConnect EP Action
                              |
                              v
                  STANDALONE_EP_VERIFIED
                              |
                              v
                 real EP self-development
                              |
                              v
               SELF_HOSTED_ENGINEERING_VERIFIED
                              |
                              v
                  Forge direct EP dogfood
                              |
       +----------------------+------------------+
       |                                         |
       v                                         v
Forge planning/derivation                 installed EP producer
(already qualified)                       proven on real repos
       |                                         |
       +----------------------+------------------+
                              v
                 Forge materialize + admit
                              |
                              v
                    P-TRANSPORT HTTP
                              |
                              v
                   EP execute/finalize
                              |
                              v
                  Forge reconcile result
                              |
                              v
                first Forge -> EP -> Forge
                              |
                              v
                  autonomous next Mission
```

## Project Intelligence planning DAG

The execution DAG above is separate from the dynamic project-intelligence loop. The latter may be prepared in parallel without blocking first execution autonomy.

```text
               canonical Project Context
                         |
                         v
                    Forge Knowledge
                         |
                         v
                   dynamic inference
                     /        \
                    v          v
           Expected Missions  Roadmap/DAG Insights
                    |          |
                    v          v
           Mission Candidates  Roadmap Change Proposals
                    |          |
                    |          v
                    |       Workspace role-aware governance
                    |          |
                    +----+-----+
                         |
                         v
                  governed Mission
                         |
                         v
                         EP
                         |
                      evidence
                         |
                         v
               refreshed Project Context
```

Canonical distinctions:

- Roadmap/Capability DAG = approved project direction;
- Expected Mission = dynamic non-canonical likely future work inferred from current Project Context;
- Mission Candidate = advisory concrete possible next Mission;
- Mission = governed canonical work;
- Roadmap/DAG Insight = Forge interpretation about plan structure;
- Roadmap Change Proposal = governed before/after changeset, advisory until approved.

Expected Missions may appear/disappear as project knowledge changes and never become hidden backlog authority. Mission Candidates are not approved work. Forge never silently mutates canonical roadmap/DAG state.

## V1 architecture preparation seams

Prepare these seams early enough to avoid incompatible later implementations, but do not block the first Forge -> EP -> Forge canary on their full UI/productization:

```text
stable roadmap/capability node IDs
        |
stable dependency-edge IDs
        |
Project Context snapshot/digest provenance
        |
Expected Mission identity/classification
        |
Mission Candidate identity/classification
        |
Roadmap Change Proposal identity + before/after diff
        |
evidence references
        |
decision type / required-role metadata
        |
FACT / INFERENCE / FORECAST / RECOMMENDATION / DECISION semantics
```

Full completion forecasting, interactive DAG editing, scenario simulation, automatic reorder proposals and multi-role Workspace approval UI are follow-on capabilities unless a concrete dependency emerges.

## Real-project qualification contracts

### DJConnect standalone canary

Required chain: P-INSTALLER-V1-qualified install -> committed declaration -> attachment -> submission -> admission -> real mutation -> canonical validation -> finalization -> immutable receipt/result/provenance -> observation. One project, one Action, serial execution.

### EP self-hosted engineering canary

A real bounded change to `pcvantol/engineering-platform` is executed by the installed CENTRAL EP. This proves the execution product can maintain its own source repository without Forge and without legacy DJConnect execution authority.

### Forge direct-EP dogfood

A real bounded change to `pcvantol/forge` is executed through EP directly, before or during Forge's orchestration integration. This avoids circular evidence: Forge does not prove its own ability to call EP using an EP path that has never independently engineered Forge.

### Workspace dogfood

A real Workspace development Action may be added after the above. It is not a prerequisite for the first Forge autonomy loop.

## Authority boundaries

| Boundary | Owner |
| --- | --- |
| Project Intelligence / Mission & roadmap reasoning | Forge |
| Canonical roadmap mutation | Existing governed project authority after applicable decision |
| Human decision UX / role-specific evidence projection | Workspace |
| Project/repository declaration | Canonical Project Authority Repository, validated by EP |
| Submission/admission/run/finalization/receipt | EP |
| HTTP submission transport | EP P-TRANSPORT |
| Run/status/evidence projection | EP |

## Readiness chain

Autonomous Mission execution is now:

```text
approved Mission + Planner/Living Graph       PROVEN
EP P-TRANSPORT HTTP                           AVAILABLE
P-NEUTRAL                                     ACTIVE EP GAP
P-INSTALLER-V1                                EP INSTALLED-PRODUCT GAP
DJConnect real execution                      EP QUALIFICATION GAP
STANDALONE_EP_VERIFIED                        EP GATE
EP self-development                           EP PRODUCER CONFIDENCE GAP
Forge direct EP dogfood                       CROSS-BOUNDARY QUALIFICATION GAP
Action materialization/admission              FORGE GAP
EP observation/reconciliation                 FORGE GAP
first Forge -> EP -> Forge canary             QUALIFICATION GAP
autonomous next-Mission repetition            FINAL EXECUTION AUTONOMY GAP
```

Project Intelligence/Workspace governance productization is deliberately not inserted into this execution readiness chain.

## Safe parallelism

- Forge may stabilize Project Context / Expected Mission / Roadmap Change Proposal contracts while live execution integration is on hold.
- Forge should not invent installed EP readiness/execution contracts ahead of real installed evidence.
- P-NEUTRAL proceeds now, followed by P-INSTALLER-V1.
- DJConnect/EP/Forge declarations and real Actions are serial qualification proofs; this does not require multi-project concurrent scheduling.
- Workspace Roadmap/DAG Governance architecture can mature separately and remain non-blocking for first machine autonomy.
- General Agent separation/dispatch/multi-host/multi-repository productization follows the first real loops unless a canary proves it necessary.

## First Forge execution canary

After the real-project producer proofs:

1. create/select one new low-risk executable Mission;
2. materialize one immutable Action snapshot;
3. persist execution-admission/submission intent with idempotency/correlation;
4. POST once through existing P-TRANSPORT HTTP;
5. observe exact canonical EP run/result evidence;
6. reconcile idempotently;
7. refresh Project Context from canonical outcome evidence;
8. stop after the first canary;
9. only then activate automatic next-Mission selection.

Forge never writes the target repository directly and never reconstructs EP authority from logs, Console state, filesystem state or direct Agent control.

## Roadmap-to-action rule

A derived node becomes ready only when its actual producer evidence exists. Historical phase labels cannot create artificial blockers, transport availability cannot be promoted to execution qualification, and Expected Missions/Mission Candidates cannot be promoted to approved roadmap or execution authority. Owner gates apply at genuine authority expansion points rather than every engineering repair/validation iteration.

Reconcile this DAG whenever canonical Forge, EP or Workspace roadmap authority changes.
