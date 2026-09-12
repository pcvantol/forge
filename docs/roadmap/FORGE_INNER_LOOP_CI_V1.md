# Forge inner-loop CI — implementation roadmap

**Capability:** `FORGE::INNER_LOOP_CI_INTEGRATION_V1`
**Status:** PLANNED implementation. **Lane:** RUNTIME_QUALIFICATION.

Implement the [test contract](../architecture/FORGE_INNER_LOOP_CI_INTEGRATION_V1.md)
and [documentary DAG](forge-inner-loop-ci-v1.json) as a core CI regression line.
The [runtime evolution roadmap](../architecture/runtime-evolution-roadmap.md)
links this work. It is independent of Console/relay/installer/Workspace work and
of the first live canary's success; its PASS does not replace that live proof.

## Existing foundation

The source snapshot in the contract already has governance/intake, dynamic
Mission, recovery and HTTP-adapter tests. Reuse their useful assertions, but do
not claim them collectively as the installed Candidate-to-completion suite:
the inspected runtime success test directly constructs a Mission, injects an
in-memory host and reopens inside the same process. Close those seams explicitly.

## Delivery DAG

| Node | Deliverable | Hard dependencies |
| --- | --- | --- |
| FCI-CONTRACT | Producer-pinned mock schemas, fixture provenance and FIE scenario registry | none |
| FCI-HARNESS | Installed-wheel isolated process runner, boundary-only provider/OS fixtures and safe cleanup | FCI-CONTRACT |
| FCI-EP | Stateful local EP HTTP simulator with strict identities, request ledger and faults | FCI-CONTRACT |
| FCI-FLOW | Public Candidate/governance/intake -> A -> real adapter -> completion success chain | FCI-HARNESS, FCI-EP |
| FCI-RESTART | Evidence-dependent successor and new-process/idempotent recovery coverage | FCI-FLOW |
| FCI-NEGATIVE | Parameterized authority, scope, provider, transport and evidence failures | FCI-FLOW |
| FCI-CI | Required CI/release integration, artifacts and qualification of the complete suite | FCI-RESTART, FCI-NEGATIVE |

```text
FCI-CONTRACT -> FCI-HARNESS --+
             -> FCI-EP -----+-> FCI-FLOW -> FCI-RESTART --+-> FCI-CI
                                        -> FCI-NEGATIVE -+
```

All seven implementation nodes remain PLANNED. FCI-CONTRACT completion requires
implemented fixture/contract validation, not this design alone. The JSON is not
a Mission/Action plan or permission to mutate a live runtime. No console graph
is extended and no peer repository work is allocated.

## Read-only, documentation and design support closure

The existing seven-node DAG now includes FIE-17..FIE-28, not a second Mission
engine or separate test lane. The [effects/output contract](../architecture/FORGE_INNER_LOOP_CI_INTEGRATION_V1.md#mission-effects-and-deliverable-modes--2026-09-12-extension)
is an explicit part of FCI-FLOW/RESTART/NEGATIVE/CI acceptance.

| Requirement | Owner | Current evidence / required closure |
| --- | --- | --- |
| FME-ADMISSION | Forge | SOURCE_GAP_OBSERVED at 2ff27234ca95b1f94c7235cc7ce12244b9cd8f69: public _admission_contract rejects empty write_scopes. Qualify effect-aware public approval/intake/planning with explicit empty writes, valid read scope and no authority weakening. |
| FME-PRODUCER | EP producer; Forge consumes | REQUIRED_EVIDENCE_UNVERIFIED: prove the actual supported effect/result schema and read-only execution/report contract. No unqualified mock fields or simulated producer claims; any necessary EP change stays EP-owned. |
| FME-COMPLETION | Forge | REQUIRED_EVIDENCE_UNVERIFIED: qualify durable useful non-Git reports, unchanged-source provenance, per-criterion evidence and mode-appropriate review/delivery without a forced PR/commit. |

These are scoped evidence requirements, not newly allocated peer work or executed
repairs. Reuse current implementation where exact qualification exists. The
known admission issue must be fixed through the normal owning product route,
not patched inside a fixture. The producer requirement gates only affected new
positive cases; it is not an added prerequisite for unrelated existing write
scenarios or the current live canary. The expanded complete-suite claim still
requires every mandatory family: fail/unsupported/skip cannot count as support.

FCI-CONTRACT defines effects, output and control applicability with real schemas;
FCI-HARNESS independently observes target effects and segregates owned scratch;
FCI-EP supplies only qualified serialized report/delivery outcomes;
FCI-FLOW qualifies all four modes through real Candidate-to-completion services;
FCI-RESTART preserves them and artifacts through fresh processes;
FCI-NEGATIVE exercises escalation, unauthorized writes and insufficient evidence;
FCI-CI makes the complete mode/scenario matrix a blocking result with artifacts.
No code/test changes are silently permitted by a documentation/design label.
An assessed no-change result differs from missing work and from write-mode no-op.
Report-only advice in a chat does not substitute for the formal read-only Mission.

## Acceptance and resumption

FCI-FLOW must start with an actual Candidate from its owning public lifecycle,
not a string used to label an already-approved Mission. Preserve its exact
revision/criteria lineage through canonical approvals, allocator and intake.
If the inspected product lacks a public connection between these stages,
record that bounded product gap and qualify its fix; do not silently bypass it.

Full delivery requires all FIE-01..FIE-28 families, real installed imports,
process restart and serialized EP HTTP evidence. A controlled LLM fixture is
expected for deterministic CI; production planning/validation/reconciliation
remain real. No real provider login/cost, EP server or GitHub mutation is needed.

FCI-CI is complete only after the suite executes on PR/main, failures fail the
protected qualification path, local reproduction is documented, and the exact
wheel/fixture identity plus per-scenario evidence are retained. Release
qualification reuses the suite before publication. Missing or skipped mandatory
scenarios are not green. A documentation test checking this plan is not E2E.

Refresh current sources, open PRs and producer contracts before implementation.
Keep the live canary's Mission, attempts, expiry, credentials and evidence intact.
New source/runtime repairs found by tests are separate bounded owning changes,
not authority to complete unrelated architecture or install another runtime.

## Later outer-loop qualification

The [outer-loop roadmap](FORGE_OUTER_LOOP_CI_V1.md) and
[documentary DAG](forge-outer-loop-ci-v1.json) consume FCI-CI, never the reverse.
They exercise M1 completion -> Context -> Candidate -> governed M2 and reuse
this same installed harness/EP simulator. Candidate-to-completion within ONE
Mission remains this suite's full boundary; next-Mission inference is the later
suite. Both keep live-provider/EP qualification separate from deterministic CI.
