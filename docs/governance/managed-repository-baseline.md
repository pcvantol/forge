# Forge Managed Repository Baseline

## Status

Forge is promoted from its Genesis history to the canonical first-class
repository [`pcvantol/forge`](https://github.com/pcvantol/forge). Managed in
this context means repository and delivery governance are managed; it does not
mean that Forge executes through the current Engineering Platform runtime.

The authoritative Genesis record is [Forge Genesis Provenance](../../FORGE_GENESIS_PROVENANCE.md).
The architecture entrypoint is the [Founding Architecture Handbook](../architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md).
Roadmap history is owned by [Bootstrap Roadmap](../../knowledge/bootstrap/10_ROADMAP.md)
and the current runtime direction by [Runtime Evolution Roadmap](../architecture/runtime-evolution-roadmap.md).

## Repository-family baseline

| Area | Reference | Forge decision | Rationale |
| --- | --- | --- | --- |
| Merge strategy | DJConnect | Squash merge only; delete merged branches | Small, reviewable delivery units without product-specific release process. |
| Main integrity | DJConnect | Active default-branch ruleset: no deletion or force push; pull requests and resolved conversations required | Protect canonical history and keep review evidence. |
| CI | DJConnect/TDE | Python standard-library tests, compilation, JSON contracts, and documentation validation | Forge currently has Python source and tests, no packaged dependency stack or UI. |
| TDE | Technical Debt Engine | Standalone public CLI integration with the Forge `.tde.yml` code-size profile; observe-only | TDE owns its policies and evidence semantics. |
| Security | Repository family | CodeQL, Dependabot for GitHub Actions, secret scanning, push protection, and `SECURITY.md` | Applies to Forge's actual Python and workflow surfaces. GitHub Dependency Review is unavailable until Forge has a supported dependency-graph surface. |

## TDE evidence profile

Forge uses the standalone Technical Debt Engine public CLI with its committed
`.tde.yml` profile. It enables only the currently applicable `code_size`
capability. TDE evidence is produced through the public CLI and its canonical
evidence location; Forge neither imports TDE internals nor defines a
repository-specific TDE policy fork.

TDE is currently not a required GitHub check: its CLI is not yet available as
a public package that GitHub Actions can deterministically install. This is an
intentional, fail-closed non-enablement rather than a fabricated CI check. The
operator can run the public command locally:

```text
tde assess --capability code_size .
tde qualify --capability code_size .
```

When TDE publishes a supported immutable consumer distribution or reusable
workflow, Forge may add that exact producer as an observe-only CI check.

## Dependency review boundary

Forge currently has no Python package manifest or other supported GitHub
dependency-graph input. GitHub Dependency Review therefore rejects this
repository rather than producing a meaningful result. It is intentionally not
configured as a failing workflow. Dependabot monitors the actual GitHub Actions
ecosystem; CodeQL and secret scanning cover the current source and workflow
surfaces. Dependency Review may be enabled when Forge adopts a supported,
deterministically declared dependency ecosystem.

## AI-development and handoff continuity

The root [BOOTSTRAP](../../BOOTSTRAP.md), [ENGINEERING_METHOD](../../ENGINEERING_METHOD.md),
[PROMPT_INITIALIZATION](../../PROMPT_INITIALIZATION.md), and [AGENTS](../../AGENTS.md)
documents remain Forge's working new-chat entrypoint. Their generic portions
are **PENDING_AI_DEVELOPMENT_CONTRACT_NORMALIZATION**. They are deliberately
retained until a canonical replacement exists.

Current Forge handoffs remain under [`docs/handoff`](../handoff/); reports and
historical evidence remain under [`docs/reports`](../reports/) and
[`docs/evidence`](../evidence/). No DJConnect documentation is required to
start safely in this repository.

## Boundaries

Forge has no source dependency on Engineering Platform. Any future interaction
uses the installed Engineering Platform through Forge's documented
Producer/Execution Host contracts. Forge and Workspace are first-class peers;
their source, governance, and runtime remain separate.
