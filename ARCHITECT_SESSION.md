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

## Reconstructing the present Project Context and critical path

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
Forge selects real work; materializes a bounded Action; submits through the
installed canonical EP boundary; EP admits, executes, validates and finalizes
a real repository mutation; EP exposes terminal result/evidence; Forge exactly
reconciles it; Forge selects/unlocks a successor; and repairable bounded
failures and successor work proceed without owner prompt/result relay.

Use the roadmap and DAG as the current critical-path evidence. For every
predecessor ask: “Does its absence physically prevent the first real Forge ->
EP -> Forge loop?” Classify `YES` as `AUTONOMY_CRITICAL`; otherwise classify it
`POST_AUTONOMY` or `PARALLEL_NON_BLOCKING`. Do not preserve historical ordering
without this test. Current direction is explicit that P-TRANSPORT has three
EP-owned ingresses (HTTP JSON, installed CLI and Server-owned File Inbox),
which converge through EP Submission Service/CENTRAL; Forge reuses canonical
HTTP rather than Local Consumer API, direct CENTRAL reads or a new transport.

The current derived path keeps P-NEUTRAL, the server-only P-INSTALLER-V1
qualification and real-project execution proofs critical when their owning EP
canonical evidence says they remain unsatisfied. Workspace implementation,
generalized Agent separation, generalized dispatch, multi-host execution,
broad queue/B8E productization, learning productization, historical cleanup
and source retirement are not first-loop blockers unless new concrete evidence
shows otherwise. Re-evaluate rather than assume.

## Governance and parallel work

Within an already authorized functional engineering envelope, ordinary
implementation, testing, review, bounded repair, re-test, exact-head
qualification, merge synchronization and reconciliation should proceed without
an owner acting as a message relay. A changed exact head is still requalified;
it is not automatically an authority change. Pause for `BUSINESS_SCOPE_CHANGE`,
`ARCHITECTURE_AUTHORITY_CHANGE`, `DESTRUCTIVE_OR_IRREVERSIBLE_DECISION`,
`SECURITY_AUTHORITY_EXPANSION`, or materially ambiguous product decisions.
Preserve required security and governance controls.

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
