# Forge inner-loop CI integration V1

**Capability:** `FORGE::INNER_LOOP_CI_INTEGRATION_V1`
**Status:** PLANNED implementation; this increment records the test contract.
**Lane:** RUNTIME_QUALIFICATION, independent of Console/POST_AUTONOMY work.

The requested boundary is the complete Forge flow from a **Mission Candidate**
to execution and completion of ONE approved Mission, with EP simulated. This is
an installed-product integration suite, not a browser test and not a replacement
for the separately authorized real Forge/EP/provider canary. The
[roadmap](../roadmap/FORGE_INNER_LOOP_CI_V1.md) and
[documentary DAG](../roadmap/forge-inner-loop-ci-v1.json) define delivery.

## Current source evidence and gap

Inspected Forge source: `1bb8635c82a8dd0385fac8022ff0d9dd90f4c028`.

| Source | What it covers / what this new layer must add |
| --- | --- |
| [ci.yml](../../.github/workflows/ci.yml) and [validate.sh](../../scripts/validate.sh) | Python 3.14 unittest discovery and static/version/projection checks; no separately named installed Candidate-to-completion job in the inspected workflow. |
| [test_installed_dynamic_mission_runtime.py](../../tests/test_installed_dynamic_mission_runtime.py) | Public bootstrap, real approval services, zero-Action admission, start, close/reopen and recovery. Constructs ArchitectureMission directly, injects an in-memory _Host and provider, and reopens in the same Python process. The filename does not itself establish wheel-installed/new-process/HTTP proof. |
| [test_mission_recommendation_lifecycle.py](../../tests/test_mission_recommendation_lifecycle.py) | Candidate/recommendation lifecycle in a standalone test store with injected Mission-ID allocator; not the whole installed canonical runtime path. |
| [test_governance_authority.py](../../tests/test_governance_authority.py) | Envelope, operator and intake guards, including public Server-root cases; do not copy its low-level unit-test bypass into the new integrated success path. |
| [test_dynamic_mission_capability.py](../../tests/test_dynamic_mission_capability.py) | Deterministic dynamic successor/containment tests with a test dispatcher and host; retain these focused tests alongside the real composition suite. |
| [test_ep_http_adapter.py](../../tests/test_ep_http_adapter.py) | Strict EP readback/artifact handling with patched transport, separately from Candidate intake and the full runtime. |

These are useful existing tests, not evidence that the complete new suite is
already delivered. Reuse fixtures/assertions where appropriate without carrying
forward an internal mock that skips the integration boundary under test.

## Test boundary: real Forge, simulated external systems

```text
Candidate via its owning public service (not just a candidate-ID string)
  -> canonical Business + Architecture decisions on its exact revision
  -> validated approval envelope + real Mission-ID allocation
  -> public Mission Intake: zero Actions
  -> installed dynamic runtime + actual planning/validation/materialization
  -> real Forge EP factory/HTTP adapter -> local stateful mock EP HTTP server
  <- submission receipt / run status / immutable terminal artifact bytes
  -> real digest/schema/identity verification + durable reconciliation
  -> actual process exit / new process opens SAME isolated instance
  -> completion evaluation OR evidence-dependent successor -> same EP boundary
  -> evidence-derived Mission completion + durable terminal readback
```

Use the current owning Candidate lifecycle and its legitimate transition order.
Preserve Candidate identity, revision, scope, criteria and approval provenance
through the entire chain. Recommendation setup needed by that lifecycle may be
a deterministic upstream input; autonomous Portfolio/outer-loop generation of
new Missions is outside V1. Do not force legacy allocation into canonical intake
by copying SQLite rows or inventing an adapter in the test. A missing production
Candidate-to-intake seam is a named implementation gap, not grounds for skipping
Candidate creation or calling a manually seeded Mission an end-to-end result.

Real components: public runtime/bootstrap composition, operator capability
checks, governance persistence, intake, allocator, planning snapshots, proposal
validation, runtime prompt generation, dispatcher/runner, EP serialization and
consumer validation, SQL/file persistence, recovery, completion evaluator and
readback. Do not stub these to return PASS or alter their internal state to move
from one test phase to the next. Fixture writes for deliberately corrupt-input
negative tests are explicit and never part of the successful lifecycle.

Simulated boundaries:
- **EP:** a bounded stateful HTTP test server on loopback/ephemeral port, not a
  mock of Forge's dispatcher, factory, adapter or evidence verifier.
- **External LLM:** deterministic responses at the external process/transport
  boundary, so normal tests require no Codex login, API key or subscription.
  Exercise the actual prompt/output parser, schema and scope validator. A fake
  Codex executable/transport may assert argv, input/schema and return serialized
  proposals/errors. It must not insert EngineeringAction objects into storage.
- **OS identity/secure store:** declared fixture identity and credentials at
  those boundaries; use normal product binding/configuration/authorization
  services. Do not replace authorization decisions themselves with stubs.
- **Repository evidence:** isolated local fixtures with declared immutable
  revisions. EP implementation, review, GitHub mutation and actual build output
  are simulated external facts, NEVER claims of real delivery or real assurance.

Deterministic provider fixtures may know how a scenario ends; the admitted
Mission must still contain zero Actions, and B is returned only after the actual
current snapshot contains A's verified evidence and an unmet approved criterion.
This proves orchestration/containment under controlled inputs, NOT LLM judgment
or live autonomous discovery. Include a single-Action-completes-all scenario;
the runtime must not invent B merely to satisfy a test's preferred story.

## Mock EP contract and isolation

The simulator implements the **supported versioned producer contract**, currently
readback/terminal-evidence v1.2, including explicit selection, compatibility,
consumer authentication, scoped submission, pending/claimed/terminal readback
and artifact download. Derive responses from captured request identities and
retain exact accepted-request digests, receipts, runs and immutable bytes. Use
producer-pinned schema/fixtures with recorded source and digest, validated
independently of Forge's serializer; no permissive fake that mirrors every bug
in the consumer. Contract updates require explicit reviewed fixture changes.

Keep the simulator independent from Forge's database and child processes, with
its own request ledger and test state. The ledger must count actual POSTs and
attempts so tests catch duplicates; it is test evidence, not an alternative
Forge runtime store. Support accept-then-disconnect, delayed completion, explicit
denial, no-run dispositions, wrong auth/instance/version, terminal failure and
missing/tampered/mismatched artifact scenarios. Unexpected methods, requests,
versions or identities fail the scenario. A generic always-success response is
not sufficient. Do not reproduce EP's internal scheduler/repair engine.

During scenario execution deny non-test network destinations, real provider/gh
execution and use of host credentials. Use fresh HOME/data-root/workspace per
scenario, no user's macOS root, Keychain, launchd, Tailscale or production ports.
Dependency installation precedes the isolated test stage; locked dependencies
need not be downloaded while the scenario is running. An attempted escape is a
FAILED test, not a skip. Clean up only owned processes/ports/temp roots on every
exit. Nothing from the suite may be imported as live runtime qualification.

## Mandatory scenario inventory

Each ID is a test family; identity/error combinations are parameterized. The
success and restart families exercise the complete public composition, not a
collection of separately green unit tests.

| ID | Required evidence |
| --- | --- |
| FIE-01 | Full Candidate -> current dual approval -> zero-Action intake -> A -> authenticated HTTP exchange -> validated artifact -> completion. Assert exact identity/criteria lineage and final idle state. |
| FIE-02 | A proves only one approved criterion; reconcile, exit, reopen and derive B from the current gap. A/history unchanged; no new owner decision; B absent before A evidence; complete only after B. |
| FIE-03 | A proves all criteria: one proposal/Action/submission, no B and no further call on completed resume. |
| FIE-04 | Candidate alone, one missing/rejected approval, wrong actor, stale Candidate revision or changed criteria: no premature Mission allocation/admission, planning or EP POST at the applicable gate. |
| FIE-05 | Missing/expired/out-of-scope execution or provider authority and exhausted applicable budget: no unauthorized new call; restart does not reset counters or expiry. |
| FIE-06 | Provider unavailable, pre-start rejection, invalid structured output and MAY_HAVE_HAPPENED: classified durable attempt, no materialization/submission and no blind regeneration. |
| FIE-07 | Invalid write scope/dependency, stale snapshot, optional improvement, already proven criterion or wider Mission objective rejected before submission. |
| FIE-08 | EP incompatible v1.2, wrong instance, wrong consumer/project/repository or auth rejected; preflight creates zero submissions, no v1.1 fallback. |
| FIE-09 | Delayed EP acceptance/claim/evidence: bounded waiting, no busy-loop or duplicate POST. Waiting is not success. |
| FIE-10 | EP accepts POST then connection is lost; fresh Forge process reconciles by supported durable identity. Otherwise remain explicitly ambiguous, never blind resubmit. |
| FIE-11 | Wrong artifact byte hash, schema, request digest, Mission/Action/correlation/run/repo/producer/profile provenance, or required assurance missing: reject before canonical evidence/completion. |
| FIE-12 | Terminal EP run without required immutable evidence: bounded contract failure, not infinite polling or fabricated evidence. Explicit decline/no-run is separately classified. |
| FIE-13 | EP FAILED/BLOCKED and supported authorized recovery retain original/retry lineage and counters; completed work is never rerun. Without authority no replacement submission. |
| FIE-14 | Duplicate/stale/out-of-order readback and repeated resume are idempotent; two concurrent starters cannot both dispatch the same immutable Action. |
| FIE-15 | New-process recovery at post-intake, post-materialization/pre-send, accepted/pre-local-ack, post-reconciliation/pre-successor and completed boundaries. Same instance, records and budgets; no shadow DB. |
| FIE-16 | Schema/marker/runtime or installed module mismatch and storage unavailable fail closed. Errors retain useful secret-free diagnostics; no replacement instance is initialized. |

Named budgets in tests must come from the applicable production policy and
fixture authorization. Do not invent an end-to-end budget guard that production
does not have. A missing required enforcement/composition seam stays a reported
gap until repaired and tested; expected-failure/skip is not completed coverage.

## CI and installed-artifact acceptance

Target one visibly named **Forge inner-loop integration (mock EP)** job in the
canonical Forge CI, on PRs and main pushes plus manual dispatch. It is a core
runtime-quality line, NOT delayed behind the Console or the live canary. Use
Python 3.14 and pinned dependencies/actions consistent with the owning workflow.
Start with an explicit bounded job (target 10 minutes) and bounded per-scenario
subprocess deadlines; record actual timings. No sleeps to simulate minutes of
EP work, no unbounded retry-until-green. Parallelize only isolated scenarios.

Build once from the exact candidate, record source/wheel digest, install into a
fresh venv and execute outside the checkout. Assert sys.executable, sys.prefix,
package/module location and representative module bytes; version alone is not
identity. Transfer only tests/fixtures into the runner, not the Forge source
package. A new process must reconstruct from public persisted config, not from
parent-process Python objects or a second implementation in the test driver.
Use supported dependency-injection boundaries for fixtures; avoid a production
"disable safety" or automatic mock fallback mode.

Emit machine-readable scenario results/JUnit, a concise stage timeline, request
counts, artifact bindings, retry/recovery reasons, test-double inventory and
redacted diagnostics on failure. Required scenario absence, skip, timeout,
collection error or setup failure is NOT PASS. Report RUNNING/WAITING as such;
reaching the provider or EP POST is not completion. Preserve failures across
attempts and let CI's exit code reflect them; no continue-on-error success gate.

Before marking CI integration delivered, wire the job into the protected merge
route (direct required check or a required aggregate depending on it) and prove
a deliberately failed required scenario blocks qualification. Do not weaken or
assume repository rules; if changing those requires unavailable authority,
report the separate gate. Verify PR, post-merge and local entrypoint parity.
Reuse the installed suite in release qualification before publication; no test
release, real GitHub mutation or wheel reinstall on the user's machine.

Coverage measures real Forge production code, not the simulator. Reuse governing
coverage contracts and report the included/unmeasured modules; high coverage
cannot replace FIE-01..16 scenario completion. Browser/Playwright Console tests,
real EP producer qualification, OS installation/auth tests and live canaries are
separate complementary layers, not substitutes for this suite.

## Completion claim and exclusions

`FORGE_INNER_LOOP_CI_PASS` means the complete named suite passed against the exact
installed Forge artifact with a recorded EP mock/contract revision. It does NOT
mean `LIVE_EP_E2E_PASS`, `REAL_PROVIDER_QUALIFIED`, real review/merge success or
that production authority exists. This documentation update does not add a new
active CI job, implement the simulator, create a Mission or change a live grant.
Missing public production composition is fixed in bounded owning increments;
never imitate it inside a test to make the suite green. No Console, installer,
Workspace, outer Mission loop or multi-repository execution is required here.
