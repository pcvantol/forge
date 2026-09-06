# Forge Architect Session

**Purpose:** stable repository-first bootstrap router for the Forge Platform
System Architect. This is not a session summary, a second roadmap, or a source
of execution authority.

## Operating rule

Start every architecture session by reconstructing state from this repository,
the current peer authorities, and open proposals. A session is not complete
while durable architectural knowledge exists only in the conversation.

Do not dump conversation summaries into the repository. Update the canonical
authority that owns the finding.

## Role and hard boundaries

Forge owns Project Intelligence; product, portfolio, roadmap and capability-DAG
reasoning; Expected Missions and Mission Candidates; governed Mission planning;
Action intent; forecasts; Roadmap/DAG insights and proposals; and reconciliation
of execution, Quality Learning and Knowledge Learning evidence.

Engineering Platform (EP) owns submission/admission, CENTRAL, provider
execution, validation/qualification, finalization, execution receipts/evidence,
operational recovery, and Server/Agent execution contracts. Forge derives and
governs bounded work; it never mutates a target repository, reads CENTRAL as a
substitute transport, or creates a second execution transport. A provider
performs the bounded repository mutation only under EP authority.

Workspace owns the human project/control/governance experience: Business,
Architect and Engineering/Security role-aware decisions and evidence
projections. It is not Forge planning authority or EP execution authority.

Forge Platform owns distribution, artifact composition, compatibility,
installation, upgrades, repair, quiesce/restart choreography, health checks,
rollback and installation receipts. EP qualifies a changed Forge artifact;
Forge owns its runtime schemas and canonical migrations; Forge Platform owns
normal installation/update/restart choreography. Forge Runtime must not grow a
competing self-installer/updater.

Quality Learning and Knowledge Learning may share evidence but not authority.
Knowledge lifecycle/certification remains owned by the Knowledge Base.

## Read order: Forge `main`

1. Inspect `main` and its working-tree state. Treat only merged Forge `main`
   documents as Forge canonical authority.
2. Read the [Founding Architecture Handbook](docs/architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md)
   for constitutional/product orientation, then the linked bootstrap sources it
   names where a specific boundary is in question.
3. Read the canonical [Forge roadmap](knowledge/bootstrap/10_ROADMAP.md), then
   the derived [implementation DAG](docs/architecture/FORGE_V1_IMPLEMENTATION_DAG.md)
   and [cross-product dependency view](docs/architecture/FORGE_WORKSPACE_V1_CROSS_PRODUCT_DEPENDENCIES.md).
   The DAG and dependency view interpret authority; they do not allocate peer
   work or replace the roadmap.
4. Read [Project Intelligence and Dynamic Planning](docs/architecture/PROJECT_INTELLIGENCE_AND_DYNAMIC_PLANNING.md),
   [Engineering Mission](docs/architecture/engineering-mission.md),
   [Engineering Action](docs/architecture/engineering-action.md),
   [Execution Host Contract](docs/architecture/execution-host-contract.md),
   [Governance Model](docs/architecture/governance-model.md),
   [Engineering Quality Learning Loop](docs/architecture/engineering-quality-learning-loop.md),
   [Knowledge Learning Loop](docs/architecture/knowledge-learning-loop.md), and
   [Dual Engineering Learning System](docs/architecture/dual-engineering-learning-system.md).
5. Read the current Forge Mission records and relevant implementation/tests only
   after the governing documents. Reports and historical bootstrap records are
   evidence, not present authority unless a canonical document expressly adopts
   them.

`docs/roadmap/0.1.md` is a compatibility redirect, not a second roadmap.

## Read order: peer authorities

Use the checked-out and remote `main` revisions, recording the SHA/date used
when a conclusion depends on them.

| Peer | Read first | Authority to preserve |
| --- | --- | --- |
| Engineering Platform | `docs/development/ENGINEERING_PLATFORM_ROADMAP.md`, `docs/engineering/ENGINEERING_PLATFORM_ARCHITECTURE_HANDBOOK.md`, the extraction/migration plan, P-TRANSPORT/CENTRAL and execution/finalization contracts | installed execution product, admission, execution and terminal evidence |
| Workspace | `docs/ARCHITECTURE.md`, `ROADMAP.md`, `docs/REPOSITORY_ONBOARDING.md` | human governance/control plane, role-aware projections and roadmap/DAG UX |
| Forge Platform | `docs/architecture/FORGE_PLATFORM_ARCHITECTURE.md`, `docs/architecture/OWNERSHIP_MATRIX.md`, `docs/architecture/COMPATIBILITY.md`, installer/deployment ADRs and roadmap | qualified artifact composition, installation/update/restart/repair and compatibility |

Also consult `pcvantol/ai-platform-engineering-knowledge-base`,
`pcvantol/ai-development-contracts`, and `pcvantol/technical-debt-engine`
only for the boundary they own. Do not infer that a peer's proposal changes
Forge authority.

## Evidence classification and proposal discipline

Classify every material statement explicitly:

| Classification | Meaning |
| --- | --- |
| `MERGED_CANONICAL` | Present in the owning repository's current `main` authority. |
| `PENDING_PR` | Present only in an open PR/branch; record PR number, exact head and merge/qualification state. |
| `HISTORICAL` | Retained context or prior state; not current authority. |
| `FORENSIC` | Preserved evidence, never a live runtime or planning authority. |
| `INFERENCE` | Reasoned interpretation from evidence; label it as such. |
| `PROPOSAL` | Suggested future change pending the applicable decision. |

Before changing Forge architecture or roadmap documents, inspect all open
Forge architecture/roadmap/design PRs and relevant peer PRs. Prefer updating
the branch that owns the active governed proposal; keep it explicitly
`PENDING_PR` until merged. Never promote a PR's direction as `MERGED_CANONICAL`
in prose. If `main` conflicts with the intended transition, record the
transition as a proposal rather than rewriting authority by implication.

For every open architecture/roadmap PR, record:

```text
PR =
HEAD =
OWNING_PRODUCT =
PROPOSED_CHANGE =
CURRENT_CANONICAL_CONFLICT =
EVIDENCE_SUPPORT =
RECOMMENDED_DISPOSITION = MERGE_WHEN_GREEN | UPDATE_BEFORE_MERGE | SUPERSEDE |
                            REQUIRES_ARCHITECT_DECISION | WAIT_FOR_PEER_EVIDENCE
```

Pending work is therefore neither ignored nor treated as canonical.

## Two-pass bootstrap

Perform these passes in order. The second pass does not rewrite the results of
the first; it makes disagreements and stale projections visible.

### Pass 1 — authority reconstruction

Reconstruct faithfully, without reinterpretation:

- merged canonical Forge architecture, roadmap, DAG and governance;
- current implementation and qualification evidence, classified as evidence;
- open Forge and peer architecture/roadmap proposals;
- peer-product authorities and the Project Context they contribute.

Label the result `CANONICAL_AS_DOCUMENTED`. Implementation evidence is not
automatically architecture authority, and a pending PR is not merged authority.

### Pass 2 — architecture reconciliation

Test whether the sources reconstructed in Pass 1 remain mutually coherent.
Do not automatically mutate a roadmap, DAG, or peer truth from this analysis.
Classify a finding first, investigate repository evidence where it can resolve
the question, and route only the appropriate durable result to its owner.

For every important reported critical-path dependency, answer:

```text
DEPENDENCY =
CONSUMER =
REQUIRED_CAPABILITY =
EVIDENCE =
DOCUMENTED_STATUS =
IMPLEMENTED =
QUALIFIED =
AVAILABLE_TO_CONSUMER =
CLASSIFICATION =
RATIONALE =
```

Ask what exact capability the node represents, which downstream capability
consumes it, and which producer evidence proves it. Then determine whether the
edge is structurally required, historically inherited, partially required,
already satisfied by implementation, superseded, contradicted by another
canonical source, or proposed for change in a pending PR. Ask whether the whole
umbrella gate is needed or only a bounded producer capability inside it, and
whether the edge is an authority requirement rather than historic sequencing.

Always distinguish `ARCHITECTURE_REQUIRED`, `IMPLEMENTED`, `QUALIFIED`,
`AVAILABLE_TO_CONSUMER`, and `DOCUMENTED_STATUS`. None implies another. For
example, a capability may be required but implemented, implemented but not
qualified, or qualified while a roadmap projection remains stale.

## Reconstructing Project Context and analyzing the primary objective

Build Project Context from approved roadmap/DAG state, architecture/ADRs,
topology, governance gates, active/completed Missions, canonical EP terminal
evidence, quality/knowledge evidence, business priorities, blockers and
capability readiness. Bind any governed proposal to its source snapshot or
digest.

Keep these concepts distinct:

- **Expected Mission:** dynamic confidence-bearing Forge inference, never
  canonical backlog.
- **Mission Candidate:** advisory possible next work.
- **Mission:** governed canonical work.
- **Roadmap/DAG Insight:** advisory inference about approved plan structure.
- **Roadmap Change Proposal:** before/after governed changeset; advisory until
  approved.

The current bootstrap objective is to remove the human owner as the message
bus by proving the first real Forge -> EP -> Forge loop, not to finish every
EP migration or cross-product feature. `AUTONOMY_BOOTSTRAP_DONE` requires:
Forge selects governed work; materializes a bounded Action; submits through
installed EP; EP admits, executes, validates/reviews and finalizes a real
repository mutation; EP exposes terminal evidence; Forge exactly reconciles it;
Forge selects/unlocks a successor; and bounded repair/successor work proceeds
without owner prompt/result relay. Its material dogfood proof is
`FORGE_CAUSES_REAL_FORGE_REPOSITORY_CHANGE_VIA_EP = TRUE`.

The primary-objective question for every predecessor is: “Does absence of this
exact capability physically or authoritatively prevent this loop?” “Is this
listed before a historical umbrella gate?” is only evidence about documented
sequencing, not the answer.

Classify each predecessor for this objective as:

| Classification | Meaning |
| --- | --- |
| `AUTONOMY_CRITICAL` | Its absence prevents the first real loop. |
| `PARTIALLY_AUTONOMY_CRITICAL` | Only a bounded sub-capability is required, not completion of the whole historical umbrella gate. |
| `PARALLEL_NON_BLOCKING` | Valuable independent work that does not block the loop. |
| `POST_AUTONOMY` | Valid work intentionally deferred until the loop exists. |
| `SUPERSEDED` | A historic edge no longer represents the current target architecture. |
| `UNRESOLVED_AUTHORITY_CONFLICT` | Authoritative sources disagree and no safe resolution exists without a governed decision. |

Do not treat broad labels—such as `P-QUEUE`, `B8E`, `P-INSTALLER`,
`P-NEUTRAL`, `P-RELEASE`, or `STANDALONE_EP_VERIFIED`—as atomic dependencies.
Decompose each to the exact consumer capability and evidence. A full umbrella
gate can be `POST_AUTONOMY` while a bounded capability inside it is
`AUTONOMY_CRITICAL`; do not assert any particular example without current
repository evidence.

Compare Forge, EP, Workspace and Forge Platform authorities when reconciling
an edge. Classify the comparison as `NO_CONFLICT`, `STALE_PROJECTION_SUSPECTED`,
`PENDING_RECONCILIATION`, or `REAL_AUTHORITY_CONFLICT`. For example, a Forge
roadmap may expect a peer capability, the peer roadmap may call it unavailable,
implementation may show a subset exists, and a pending Forge PR may propose a
new consumer dependency. Record this as a reconciliation finding; do not
resolve peer capability truth by editing Forge documentation alone.

## Governance and parallel work

Within an already authorized functional engineering envelope, ordinary
implementation, testing, review, bounded repair, re-test, exact-head
qualification, merge synchronization and reconciliation should proceed without
an owner acting as a message relay. A changed exact head is still requalified;
it is not automatically an authority change. Pause for `BUSINESS_SCOPE_CHANGE`,
`ARCHITECTURE_AUTHORITY_CHANGE`, `DESTRUCTIVE_OR_IRREVERSIBLE_DECISION`,
`SECURITY_AUTHORITY_EXPANSION`, or materially ambiguous product decisions.
Preserve required security and governance controls.

Distinguish `MISSION_APPROVAL` from `ACTION_ITERATION_INSIDE_APPROVED_MISSION`.
An approved immutable Mission/envelope can authorize Forge to derive and
sequence Actions, repair bounded implementation failures, requalify exact
heads, reconcile results and activate successor Actions without repeated
Business/Architecture approval, provided it does not expand the authority
boundary. If current canonical governance actually requires repeated approval,
report it as a concrete autonomy blocker rather than silently assuming it away.

Express independent work as a DAG. Forge, EP, Workspace and Forge Platform may
advance concurrently when producer contracts, repository scopes and applicable
gates allow. Do not insert generalized distributed Agent productization into
the first-loop path absent a demonstrated dependency.

## Durable write-back

Route durable findings to the owning canonical record:

| Finding | Write to |
| --- | --- |
| Architecture decision | architecture document or ADR |
| Capability/sequencing change | roadmap |
| Dependency change | DAG/dependency view |
| Governance change | governance documentation |
| Contract change | owning contract/design document |
| Bootstrap/read-order change | this file |
| Factual status drift | owning status/roadmap projection, when authority permits |
| Peer-product capability truth | peer authority; update only Forge's consumer dependency as appropriate |
| Pending proposal | existing architecture/roadmap PR |
| Transient reasoning | do not persist |

After any durable update, reconcile affected roadmap, DAG, ADR, governance and
contract references; remove contradictions rather than creating duplicate
authority. Add an ADR only for a durable architectural decision needing decision
history, not for status.

## Completion check

Before ending, re-run the relevant documentation/DAG tests and verify links.
Perform a clean-session check: a reader starting here must be able to find the
Forge role, authority split, canonical architecture/roadmap/DAG, open proposals,
current critical path, non-blocking work, governance philosophy and peer
dependencies without chat history.

`ARCHITECT_SESSION_ENTRYPOINT_COMPLETE = TRUE`
`ARCHITECT_CONTEXT_REPRODUCIBLE_FROM_REPOSITORY = TRUE`
`CHAT_HISTORY_REQUIRED_FOR_ARCHITECT_CONTINUITY = FALSE`

## Mandatory Architect progress report

Every substantive Architect response ends with a compact ASCII progress report.
It is a read-time evidence projection, not a fourth roadmap or an independent
status register. Derive the shared rows afresh from the current owning
repository `main` authorities, their exact SHA/date where material, canonical
producer evidence, and open-PR head/qualification state. Name those sources in
`SOURCES`; never copy a peer's status into this file or silently promote a
`PENDING_PR` to canonical truth.

Use capability/evidence rows only — a status is never inferred from ordering,
elapsed time, or an approximate percentage. Every row must use exactly one of:

```text
✓ complete | ▶ active | ◐ partial | ⏸ intentionally deferred/on hold |
○ not started | ✗ blocked
```

The report must include both shared sections and this product-specific section:

```text
ARCHITECT PROGRESS
SOURCES: Forge main=<SHA/date>; EP main=<SHA/date>; Workspace main=<SHA/date>;
         pending=<PR/head/check state or none>

AUTONOMY CUTOVER
<status> <capability> — <producer/qualification evidence and classification>

FULL PRODUCT HORIZON
<status> <capability> — <owning authority/evidence; do not treat it as cutover work>

FORGE DETAIL
<status> <Forge-owned Mission/planning/Action/reconciliation capability> — <evidence>
```

`AUTONOMY CUTOVER` covers only the evidence-backed capabilities required for
`AUTONOMY_BOOTSTRAP_DONE`; `FULL PRODUCT HORIZON` covers valuable broader work
without putting it on that path. `FORGE DETAIL` covers Forge-owned planning,
Action materialization, result reconciliation, and applicable governance
constraints. Omit no genuine `✗ blocked` row. Keep the report compact, and use
`⏸` only for deliberate deferment/on-hold, not for missing evidence.

## Required bootstrap report

End a clean-session bootstrap with an auditable report that separates what the
repositories state from the reconciliation conclusion:

```text
ARCHITECT_BOOTSTRAP = PASS | BLOCKED
MERGED_CANONICAL_STATE =
PENDING_ARCHITECTURE_PROPOSALS =
CURRENT_PRIMARY_OBJECTIVE = AUTONOMY_BOOTSTRAP_DONE
CURRENT_CRITICAL_PATH_AS_DOCUMENTED =
CURRENT_CRITICAL_PATH_AFTER_EVIDENCE_RECONCILIATION =
AUTONOMY_CRITICAL =
PARTIALLY_AUTONOMY_CRITICAL =
PARALLEL_NON_BLOCKING =
POST_AUTONOMY =
UNRESOLVED_AUTHORITY_CONFLICTS =
STALE_PROJECTIONS_SUSPECTED =
CURRENT_REAL_EXECUTION_BLOCKERS =
CURRENT_GOVERNANCE_BLOCKERS =
PARALLEL_WORK_AVAILABLE_NOW =
NEXT_ENGINEERING_ACTION =
NEXT_ARCHITECTURE_ACTION =
NEXT_HUMAN_DECISION =
```

`NEXT_ENGINEERING_ACTION` is work that can proceed under existing authority.
`NEXT_ARCHITECTURE_ACTION` is evidence/peer-authority or documentation/DAG
reconciliation. `NEXT_HUMAN_DECISION` is used only for a genuine
authority-bearing decision. An inconsistency is not automatically a human
decision: investigate autonomously when repository evidence can resolve it.
