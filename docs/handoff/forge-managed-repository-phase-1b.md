# Forge Phase-1B Repository-Family Handoff

## Canonical identity

- Repository: [`pcvantol/forge`](https://github.com/pcvantol/forge)
- Genesis source: `/Users/pcvantol/Documents/GitHub/forge`
- Genesis source `HEAD` at promotion: `766539b3c15a35b5eead841da77117c8365e0ef0`
- Canonical initial `main`: `766539b3c15a35b5eead841da77117c8365e0ef0`
- History result: the complete Genesis ancestry is preserved without rewrite or
  reimplementation.

## Canonical Forge entrypoints

- Architecture: [Founding Architecture Handbook](../architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md)
- Roadmap: [Bootstrap Roadmap](../../knowledge/bootstrap/10_ROADMAP.md) and
  [Runtime Evolution Roadmap](../architecture/runtime-evolution-roadmap.md)
- Development/bootstrap: [BOOTSTRAP](../../BOOTSTRAP.md),
  [ENGINEERING_METHOD](../../ENGINEERING_METHOD.md),
  [PROMPT_INITIALIZATION](../../PROMPT_INITIALIZATION.md), and
  [AGENTS](../../AGENTS.md)
- Managed governance: [Managed Repository Baseline](../governance/managed-repository-baseline.md)
- Provenance: [Forge Genesis Provenance](../../FORGE_GENESIS_PROVENANCE.md)

## Retained generic-governance candidates

The root `BOOTSTRAP.md`, `ENGINEERING_METHOD.md`, `PROMPT_INITIALIZATION.md`,
and `AGENTS.md`, together with historic bootstrap reports and handoffs, remain
functional Forge material. Their generic portions are
**PENDING_AI_DEVELOPMENT_CONTRACT_NORMALIZATION**. They must be considered by
the later `ai-development-contracts` projection work; this Phase-1B promotion
does not delete or migrate them.

## TDE integration

Forge uses the standalone Technical Debt Engine through the public CLI and
committed [`.tde.yml`](../../.tde.yml) `code_size` profile. The profile was
validated, assessed, and qualified locally. TDE remains observe-only and is
not a required GitHub check because a deterministic public CI consumer
distribution is not available.

## Managed status

Forge is a first-class managed repository: canonical remote and `main`, full
history preservation, description/topics, labels, PR/issue templates,
squash-only delivery, auto-delete, active main ruleset, Forge CI, CodeQL,
Dependabot for GitHub Actions, secret scanning/push protection, security
policy, and standalone bootstrap/handoff entrypoints are present.

Forge does not import Engineering Platform source and does not own Workspace.
Both remain first-class peers through their documented contracts. Production
action for this promotion is **NONE**.
