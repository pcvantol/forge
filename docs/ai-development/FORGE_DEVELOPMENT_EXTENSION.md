# Forge development extension

This is the locally authored companion to the generated
[AI-development projection](GENERATED_PROJECTION.md). It does not replace or
repeat the eight generic contracts. It records only rules and navigation that
exist because this repository engineers Forge.

## Forge-local orientation and provenance

Start with [BOOTSTRAP.md](../../BOOTSTRAP.md), then the
[Founding Architecture Handbook](../architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md),
the [Bootstrap Roadmap](../../knowledge/bootstrap/10_ROADMAP.md), current
[runtime evolution roadmap](../architecture/runtime-evolution-roadmap.md), and
[Forge Genesis Provenance](../../FORGE_GENESIS_PROVENANCE.md). Genesis reports,
handoffs and commits are retained as Forge historical evidence; they are not
alternate generic contract authorities.

## Forge product and governance authority

Forge owns its architecture, Vision/Roadmap/Backlog and increment planning,
Engineering Intent and Mission models, orchestration, repository truth,
provider/model strategy, Forge-specific validation, and Forge product behavior.
The canonical records are the architecture handbook and its linked product,
planning, Mission, Intent, Producer, Runtime and governance documents.

Business owns portfolio value and Business approval; Architecture owns
technical refinement and Architecture approval. Mission Intake admits an
already-approved Mission into durable Forge state. These are Forge product
boundaries, not generic prompt mechanics.

## Peer and integration boundaries

Workspace is a first-class peer. Forge may describe and coordinate a Forge ↔
Workspace integration, but does not own Workspace source, architecture,
governance, releases or product behavior.

Forge plans engineering and interprets evidence. A future installed Engineering
Platform executes through the versioned [Execution Host Contract](../architecture/execution-host-contract.md)
and [Producer Contract](../architecture/producer-contract.md). Forge does not
embed the Engineering Platform runtime, scheduler, provider execution, Project
Agent, store or evidence implementation.

Technical Debt Engine remains product authority for TDE implementation,
policies, evidence semantics, release and security. Forge owns only its
committed [`.tde.yml`](../../.tde.yml) `code_size` profile, Forge-specific
evidence references and this integration navigation. The profile is
observe-only and not a hosted required check until TDE publishes a deterministic
consumer distribution or reusable workflow.

## Forge-local validation and handoff

Run `bash scripts/validate.sh` for Forge's standard-library compilation,
tests, JSON-contract checks and projection validation. Run `tde validate`,
`tde assess --capability code_size .`, and `tde qualify --capability code_size .`
when TDE evidence is required. The local handoff entrypoint is
[Phase-1B Repository-Family Handoff](../handoff/forge-managed-repository-phase-1b.md);
current adoption evidence is the
[semantic-equivalence receipt](../governance/AI_DEVELOPMENT_CONTRACT_SEMANTIC_EQUIVALENCE_RECEIPT.md).

Repository-local GitHub rules, security settings and delivery configuration are
actual repository state. Their Forge baseline is documented in
[Managed Repository Baseline](../governance/managed-repository-baseline.md).
