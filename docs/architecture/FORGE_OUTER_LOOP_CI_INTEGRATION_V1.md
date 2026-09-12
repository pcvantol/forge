# Forge deterministic outer-loop CI integration V1

**Capability:** `FORGE::OUTER_LOOP_CI_INTEGRATION_V1`
**Status:** PLANNED; specification only, no new CI job or runtime implementation.
**Sequence:** later than the [inner-loop CI suite](FORGE_INNER_LOOP_CI_INTEGRATION_V1.md).
The [scoped roadmap](../roadmap/FORGE_OUTER_LOOP_CI_V1.md) and
[documentary DAG](../roadmap/forge-outer-loop-ci-v1.json) define this follow-on.

## Boundary and source evidence

The inner loop executes ONE approved Mission, including its necessary Actions.
The outer loop consumes its outcome to refresh Project Context and infer possible
NEXT Missions. These are different qualification boundaries. Candidate discovery
is not approval, and a completed Mission cannot authorize the next Mission.

Source reviewed: Forge `206657698bb29caa6d22fda5020e4ebc8072700f`.
The inner-loop specification and seven FCI nodes are already documented by PR94,
but remain PLANNED implementation. Existing composition tests cover useful slices;
[test_installed_dynamic_mission_runtime.py](../../tests/test_installed_dynamic_mission_runtime.py)
injects an in-memory host, constructs an ArchitectureMission and reopens in one
Python process. It is not the complete installed Candidate-to-completion or
outer-loop suite. [ci.yml](../../.github/workflows/ci.yml) currently calls the
normal validation script; this document does not claim a dedicated job exists.

## Required end-to-end scenario

```text
M1 completes through the real Forge inner loop against mock EP
  -> verified canonical outcome and completion evidence
  -> real Project Context refresh and snapshot/provenance
  -> Expected Missions / recommendations (advisory)
  -> Mission Candidate via its owning lifecycle
  -> portfolio/duplicate/stale-context decisions
  -> WAIT for applicable Business and Architecture approval
  -> explicit fixture approvals through REAL governance services
  -> canonical M2 allocation/intake, initially zero Actions
  -> same real inner-loop composition, with EP still mocked
  -> verified M2 completion -> context refresh -> no-op or governed next proposal
```

No test driver may inject a pre-approved M2, write COMPLETE directly, fabricate
canonical receipts or implement the outer loop itself. If an existing public
production seam is missing, record and deliver that bounded seam separately;
do not replace it with test-side orchestration and call the result integration.
Human input is deterministic fixture input to real authorization/approval
services, not mocked approval decisions or new production auto-approval policy.
A negative test must stop at an unapproved Candidate with zero M2 allocations,
Actions or submissions at the relevant admission boundary.

Recommendations, Expected Missions, Candidates, Roadmap Change Proposals and
approved Missions keep distinct identities and authorities. Suggestions do not
silently change canonical roadmap priority, scope, grants or execution policy.
Failure/blocked/ambiguous M1 outcomes take their own product paths; they are not
success inputs and do not create a replacement Mission to reset a repair budget.
An actually complete project yields an idle/no-candidate outcome, not busywork.

## Determinism and mock boundary

Reuse FCI-HARNESS and FCI-EP, not a second simulator. Run the installed Forge
wheel outside its checkout with real persistence, public application services,
proposal validation, governance, scheduler/runner, HTTP consumer, artifact-byte
verification and completion evaluation. The stateful EP mock stays at the HTTP
boundary, with independent request/receipt/artifact identities and fault ledger.
EP implementation/assurance/Git mutation are simulated facts, never real delivery.

External LLM process/transport, OS identity/secret store and upstream repository
observations use explicit deterministic fixtures. Control the clock and external
ordering; compare canonical decisions, source snapshot digests, lineage and call
counts. Generated IDs/timestamps may only be normalized in assertion output,
never rewritten in product storage. Repeated identical inputs must not create
new Candidates or Missions unless the current explicit policy permits a new one.
Changed evidence must cause the expected different decision.

No real Codex login, paid model calls, EP installation, Keychain, launchd,
Tailscale or GitHub mutation is needed. Deny non-test network/process execution
during scenarios. Fixture knowledge of a scenario is not proof of LLM judgment.
Keep data-root and upstream inputs isolated per test; bound subprocess lifetime
and clean only owned resources on every exit.

## Mandatory scenario families

| ID | Required behavior |
| --- | --- |
| FOE-01 | M1 -> verified outcome -> Context -> Candidate -> real fixture approvals -> M2 -> completion. Exact source, criteria and governance lineage throughout. |
| FOE-02 | Unapproved, rejected, wrong-role or partially approved Candidate creates no executable M2; explicit current approvals allow normal intake. |
| FOE-03 | Repeated outcome delivery, repeated ticks and concurrent observers produce one context application and no duplicate Candidate/Mission for the same identity. |
| FOE-04 | New evidence invalidates stale recommendations; old Candidate revisions/approvals cannot execute changed scope. A valid amendment follows owning governance. |
| FOE-05 | No remaining approved project gap means no Candidate, no extra planning/submission, and bounded idle behavior. |
| FOE-06 | Failed/blocked/ambiguous M1 never becomes completed context. Recovery remains exact-lineage; no fresh Mission to bypass budgets or ambiguity. |
| FOE-07 | Restart after M1 reconciliation, context refresh, Candidate persistence and approvals: SAME instance resumes once, with immutable M1 history and preserved counters. |
| FOE-08 | Invalid/tampered/incomplete outcome evidence or cross-project input is rejected before Context/Candidate updates; provenance and project isolation hold. |
| FOE-09 | Expired authority, wider scope, optional improvement, duplicate work and exhausted applicable progression limits fail closed without new execution. |
| FOE-10 | Identical fixtures produce equivalent canonical decisions/counts; changed evidence changes the correct decision. Installed artifacts, no external side effects and bounded cleanup are verified. |

Use actual supported policy limits; do not claim an unimplemented global budget
is enforced. A missing mandatory capability remains an implementation gap, not
a skipped or expected-failure scenario counted as delivered.

## CI acceptance and evidence

Add a later, visibly distinct **Forge outer-loop integration (deterministic,
mock EP)** job alongside the inner-loop job in canonical Forge CI. Require PR,
main-push and manual execution, local reproduction, Python 3.14 installed-wheel
identity, a bounded job/per-process deadline, zero automatic reruns to mask faults,
and read-only workflow permissions. Reuse the suite in release qualification.

The required-check/aggregate path must actually fail on failed, missing, skipped,
timed-out or uncollected required scenarios. Retain scenario/JUnit results,
source/wheel and fixture-contract digests, normalized decision traces, original
identity lineage, simulated EP request counts and secret-free diagnostics.
Include unchanged/replay/concurrent cases, not only a happy path. Compare like
fixtures across repeated runs without deleting failed-attempt evidence.

Measure the real Forge production scope under the existing coverage contract;
simulator lines cannot inflate it. Coverage is complementary to FOE-01..10,
not a substitute for them. Mock-CI PASS is NOT live EP/provider qualification,
server service installation, real GitHub delivery or a production execution grant.

## Independent server follow-on

After the CURRENT live E2E run is concluded and its actual result reviewed,
implement the standalone installed Forge Server process as the backend milestone
of the existing [FSH-SERVICES plan](../roadmap/FORGE_CONSOLE_HOSTING_V1.md).
A reviewed BLOCKED outcome is not relabelled PASS; it informs scope/selection.
Do not make completion of the new server, Console or this suite a prerequisite
for finishing/reporting that already-running E2E attempt.

Reuse InstalledDynamicMissionRuntime and ForgeRuntimeService: one installed
foreground serve composition, graceful shutdown, bounded polling/wakeups,
single-writer protection and durable resume, with its own product-owned API and
subsequent launchd lifecycle qualification. A class named Service or CLI storage
init is not already a deployed server. Server-only delivery must be possible
before Console/relay: no GUI/browser dependency and no second runtime database.
Server/Console/relay stay the three target service identities previously approved.

Inner-loop CI and the application-level outer suite do not depend on that daemon.
Once its production entrypoint exists, run the same scenarios through it as an
additional transport/process variant; do not fork the Mission logic or substitute
Linux process tests for macOS installed launchd/account qualification. Existing
CENTRAL, peer/provider bindings and budgets must survive service restart.
This source update creates no daemon, install, live Mission or new authority.
