# Forge handoff

This is Forge's local handoff navigation entrypoint. It does not restate the
generic handoff contract.

## Current aggregate-health handoff

Implementation PR #125 is merged at
`9208cc8ff0f6582a936a861a8c8bfa67f320989b`. It delivers the deterministic,
read-only evaluator in [`forge/runtime/health.py`](forge/runtime/health.py), its
public runtime exports, and 15 focused regressions. The exact reviewed candidate
`1d6a6faef5efb0a4aa57aea6bdf251a1a722a872` passed the focused health suite,
the aggregate-health roadmap suite, and the 666-test canonical validation, with
distinct passing Quality and Security reviews.

The delivery covers scoped liveness/readiness aggregation, required/optional/
disabled applicability, fail-closed freshness, identity and check-scope
binding, deterministic precedence, and a dependency-level proof that evaluation
does not call domain mutation or provider code. It does not deliver probes,
HTTP/CLI routes, authentication, an installed server, OpenAPI/Postman parity,
or full FH qualification. The Security review retained one non-blocking
follow-up: normalize timestamp arithmetic to UTC and regress a same-zone
daylight-saving fold before installed collectors rely on local-zone timestamps.

Engineering Platform owns the immutable Prompt History and execution receipts;
do not rewrite either as Forge product authority. Repository-local run handoff
records under `docs/engineering/runs/` are durable navigation to the bounded
delivery, not a duplicate execution-history store.

1. Start with [BOOTSTRAP.md](BOOTSTRAP.md), the committed generic projection,
   and [the Forge development extension](docs/ai-development/FORGE_DEVELOPMENT_EXTENSION.md).
2. Review the [Founding Architecture Handbook](docs/architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md),
   [current roadmap](knowledge/bootstrap/10_ROADMAP.md), and
   [Genesis provenance](FORGE_GENESIS_PROVENANCE.md).
3. Validate a bounded change with `bash scripts/validate.sh` and record the
   Forge-specific result in the handoff.
4. For the Engineering Platform terminal-evidence v1.4 adapter increment,
   see [Forge–EP v1.4 producer readback](docs/handoff/forge-ep-v14-producer-readback.md).

Forge remains a first-class peer of Workspace. An installed Engineering
Platform may serve as an Execution Host, but its source checkout is not a
Forge runtime dependency.
