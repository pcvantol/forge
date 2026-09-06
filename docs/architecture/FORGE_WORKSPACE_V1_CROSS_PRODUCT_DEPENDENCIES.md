# Forge / Workspace / EP V1 Cross-Product Dependency View

> **DERIVED DEPENDENCY VIEW.** Product roadmaps remain authoritative for their own implementation and qualification.

## Current bootstrap graph — 2026-09-06

```text
EP::P_TRANSPORT_V1 [MERGED/AVAILABLE transport]
        |
        v
EP::P_NEUTRAL_V1 [ACTIVE]
        |
        v
EP::MINIMUM_INSTALLED_EXECUTION_V1
        |
        v
EP::STANDALONE_EP_VERIFIED
        |
        +--------------------------+
        |                          |
        v                          v
Forge::FIRST_EXECUTABLE_F3_F4   Workspace future installed adapter/onboarding
        |
        v
Forge::FIRST_EP_CANARY
        |
        v
Forge::AUTONOMOUS_NEXT_MISSION_LOOP
```

Broader Agent separation/generalized dispatch, multi-host scheduling, multi-repository parallelism and unrelated B8E parity work are follow-on EP capabilities unless the minimum installed canary proves a concrete dependency.

## Current node index

| Node | Owner | Current state | Provides / consumed by |
| --- | --- | --- | --- |
| `EP::LOCAL_CONSUMER_API_V1` | EP | QUALIFIED | Consumer identity/auth/read foundation. Distinct from later P-TRANSPORT submission HTTP. |
| `EP::P_TRANSPORT_V1` | EP | MERGED / QUALIFIED transport | HTTP, installed CLI and Server-owned File Inbox canonical submission ingress. Forge should reuse HTTP. |
| `EP::P_NEUTRAL_V1` | EP | ACTIVE | Zero active generic DJConnect platform identity/authority in qualified scope. |
| `EP::MINIMUM_INSTALLED_EXECUTION_V1` | EP | QUALIFICATION TARGET | One canonical submission -> admission -> execution -> finalization -> receipt/result chain using current installed execution path. |
| `EP::STANDALONE_EP_VERIFIED` | EP | WAITING P-NEUTRAL + minimum execution proof | Installed independent execution authority for consumer canary integration. |
| `Forge::FIRST_EXECUTABLE_F3_F4` | Forge | CONTRACT-FIRST / LIVE WAITS EP | Action materialization, execution admission, HTTP submission binding, observation and reconciliation. |
| `Forge::FIRST_EP_CANARY` | Forge + EP boundary | WAITING STANDALONE | One bounded Forge -> EP -> Forge execution, one repo/action/submission. |
| `Forge::AUTONOMOUS_NEXT_MISSION_LOOP` | Forge | WAITS FIRST CANARY | Reconcile outcome -> determine/refine next candidate/Mission -> repeat under governance. |
| `Workspace::ONBOARDING_CONTROL_PLANE_V1` | Workspace | FUTURE / NOT FIRST-CANARY BLOCKER | Human/project UX and permitted intent over qualified producer contracts. |
| `EP::GENERALIZED_AGENT_DISPATCH_V1` | EP | FOLLOW_ON | Broader Agent separation/dispatch/multi-host resilience. |
| `EP::MULTI_REPOSITORY_EXECUTION_V1` | EP | FOLLOW_ON | Parallel/multi-repo scheduling, leases/capacity/ordering. |
| `Forge::L2_L3_QUALITY_LEARNING` | Forge | FOLLOW_ON | Quality observation/proposals after stable Action outcome contract. |
| Knowledge/KB surfaces | Forge/Workspace/KB | POST_V1 | Additive read/proposal learning; never standalone blocker. |

## Authority corrections

### Project identity

B8R is current EP architecture. Durable project/repository identity is declared in the Canonical Project Authority Repository at `.engineering-platform/repository.json` and validated by EP. Workspace may project it and own mutable human-facing project state/display names, but Workspace availability is not required for independent EP attachment.

### Submission transport

The earlier Phase-1 Local Consumer API was initially qualified as read-only. P-TRANSPORT later added canonical mutating submission transport. Therefore:

`EP_HTTP_ALL_READ_ONLY = FALSE`

`P_TRANSPORT_HTTP_SUBMISSION_AVAILABLE = TRUE`

Forge must not create a parallel mutation transport merely because older Phase-1 documentation says its original endpoints were read-only.

### Execution versus productization

`EP::STANDALONE_EP_VERIFIED` requires proof of an independent installed execution authority, not completion of every future topology/scheduling feature. The minimum one-run canary may use the existing installed execution path. Any concrete missing queue/lease/recovery/finalization capability becomes a bounded prerequisite only when evidence shows the canary needs it.

## Directed edges

| Producer | Consumer | Contract / qualification |
| --- | --- | --- |
| `EP::P_TRANSPORT_V1` | `EP::MINIMUM_INSTALLED_EXECUTION_V1` | Canonical submission transport; transport alone is not execution qualification. |
| `EP::P_NEUTRAL_V1` | `EP::STANDALONE_EP_VERIFIED` | No legacy generic platform identity required by installed authority. |
| `EP::MINIMUM_INSTALLED_EXECUTION_V1` | `EP::STANDALONE_EP_VERIFIED` | One real installed governed execution with finalization and immutable result evidence. |
| `EP::STANDALONE_EP_VERIFIED` | `Forge::FIRST_EXECUTABLE_F3_F4` | Live installed producer available; Forge can complete HTTP submission/observation/reconciliation integration. |
| `Forge::FIRST_EXECUTABLE_F3_F4` | `Forge::FIRST_EP_CANARY` | Materialized/admitted Action and exact EP correlation contract. |
| `Forge::FIRST_EP_CANARY` | `Forge::AUTONOMOUS_NEXT_MISSION_LOOP` | Proven complete machine loop before automatic repetition. |
| `EP::STANDALONE_EP_VERIFIED` | `Workspace::ONBOARDING_CONTROL_PLANE_V1` | Allows later installed adapter/onboarding qualification; not reciprocal. |

There is no edge from Workspace to the first Forge execution canary and no default edge from generalized Agent dispatch/multi-repository execution to `EP::STANDALONE_EP_VERIFIED`.

## Safe parallelism

- Forge may build deterministic Action materialization/admission and HTTP contract fixtures while EP completes P-NEUTRAL/standalone qualification.
- Forge live integration completion waits for `EP::STANDALONE_EP_VERIFIED`.
- Workspace may design fixtures/UX but is not needed for the first machine loop.
- Broader EP Agent/dispatch/queue work may proceed separately but must not be presented as bootstrap blocking without evidence.
- Quality/Knowledge work remains nonblocking.

## Invariants

`DUPLICATE_EXECUTION_AUTHORITY = 0`

`FORGE_DIRECT_EP_DATABASE_ACCESS = FALSE`

`FORGE_DIRECT_AGENT_CONTROL = FALSE`

`WORKSPACE_EXECUTION_AUTHORITY = FALSE`

`P_TRANSPORT_DUPLICATE_FORGE_TRANSPORT = FALSE`

`FIRST_CANARY_REPOSITORY_COUNT = 1`

`FIRST_CANARY_AUTOMATIC_RESUBMIT = FALSE`

`CROSS_PRODUCT_BOOTSTRAP_DEPENDENCY_CYCLES = 0`
