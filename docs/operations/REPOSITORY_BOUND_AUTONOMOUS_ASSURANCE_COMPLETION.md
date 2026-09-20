# Repository-bound autonomous assurance and Mission-scoped merge delegation

Status: delivered, published, installed and owner-selected on 20 September 2026. This is a
sanitized public projection; private operational receipts, backups, credentials,
local roots and authorization payloads remain in the owning evidence store.

## Product boundary

Engineering Platform (EP) owns the `repository-autonomous-qs@1` profile,
installation-owner target selection, effective GitHub policy qualification,
Mission-scoped delegation and merge authority. Forge consumes the existing
versioned delegation readback for its approved Mission. The historical
`qualification-autonomous-qs@1` profile remains confined to
`pcvantol/forge-mission-qualification`; no existing grant is broadened.

The new EP source [PR #288](https://github.com/pcvantol/engineering-platform/pull/288)
merged through protected `main` at
`66fc1b143fb7cbbf998c4b85c6dbe988d89ceb02` (candidate
`15d0c739819eef3f6e4faf4c384fd6a95843b21b`). Required validation,
security, CodeQL, trusted-delivery and browser gates passed. Independent
read-only Quality and Security source reviews identified target-reselection
and GitHub StatusContext gaps, both fixed before the final gate. EP 2.3.89
introduces server schema 72; Forge source and release remain unchanged.

A clean local wheel built from the exact protected EP commit passed the EP
production-wheel qualification. Its archive digest differs from the isolated
candidate while all 164 wheel members are byte-identical. The
[EP 2.3.89 release operation](https://github.com/pcvantol/engineering-platform/actions/runs/35494712820)
completed `RELEASE_COMPLETE` and published
[`engineering-platform-v2.3.89`](https://github.com/pcvantol/engineering-platform/releases/tag/engineering-platform-v2.3.89)
from that same protected commit. Independent PyPI download and release receipt
agree on wheel SHA-256
`1ac3c5f1447b8d6ad54a50acfb17de3e6beb4faac6813bc4535f388152dcafcb`
and sdist SHA-256
`43b9f8d1d64b066ba76cbec0de66ccbe16da960a29c73175e09e053dcd0f24aa`.
All 164 published wheel members match the local protected-source wheel.

## New profile qualification on the synthetic target

The installed, non-editable candidate wheel ran on an isolated EP development
service. The owner CLI inspected the current effective policy, selected
`repository-autonomous-qs@1` for the registered
`pcvantol/forge-mission-qualification` target, reserved a grant, then
activated it only after Forge admitted the separately approved synthetic
`<SYNTHETIC_MISSION_A>`. That Mission requested one bounded source refactor; it was not a
production Mission or a replay of MISSION-0017.

The distinct isolated EP run completed. Distinct
candidate-bound Quality and Security assessments passed for each of the
IMPLEMENTATION, FINALIZATION and RECONCILIATION candidates. EP merged the
three protected target PRs through its own expected-head route:

| Role | Target PR | Candidate | Merge commit |
| --- | --- | --- | --- |
| IMPLEMENTATION | [#34](https://github.com/pcvantol/forge-mission-qualification/pull/34) | `f6da8b9b495579d4916d12122e5d7b10bb4b10db` | `6357970a4012c5c04bccd205bbc406bb9b73bc0d` |
| FINALIZATION | [#35](https://github.com/pcvantol/forge-mission-qualification/pull/35) | `f5e409754845d8aca28d7d1472580ebec1d8456c` | `ffbbf21daaed4c46e77de9a32ed715861684b281` |
| RECONCILIATION | [#36](https://github.com/pcvantol/forge-mission-qualification/pull/36) | `7c18eb8bf88ad640ee609c6c7a198debdfcfda52` | `dd8892506e942df12940850772277c43cdc44c1c` |

Each PR passed the existing `Qualification smoke` check. The effective policy
required PR delivery and resolved review threads, with zero account approvals.
Forge independently completed `<SYNTHETIC_MISSION_A>` with its required criteria proven.
The test grant and target selection were then revoked through the owner CLI;
their historical records remain immutable.

## Production target and Mission boundary

The owning EP user-service updater operation `<EP_UPDATE_A>` reached
`COMPLETE` with inventory, quiescence, protected backup, schema 71→72
migration, activation and verification. Installed EP reports 2.3.89/schema
72, the exact published wheel digest, healthy service and an empty valid
operational generation. The same installation identity was retained.
Project, repository, local binding and credential records, and pre-existing
execution history matched their protected pre-update snapshot. The
installation record's schema version changed as intended. Forge 2.7.26/
schema 39 was unchanged; installed Forge's normal authenticated
Keychain→EP preflight returned `PASS`.

The existing registered `forge` project and `forge` authority repository
resolve to the actual GitHub origin `pcvantol/forge`. The owner used the
installed `inspect-assurance-target` command, then the installed
`select-assurance-target` command with expected revision 0. A separate
readback confirms owner selection revision 1 for
`repository-autonomous-qs@1` and `target_profile_ready=true`.
The effective main policy requires a PR, `Test and static validation`,
resolved review threads and zero account approvals. No protection or ruleset
was changed. There are zero production Mission merge delegations; the
target decision selects a repository/profile only and approves no future
Mission or PR.

For a later, separately approved production Mission, use these installed
commands. `EP_ROOT` and `FORGE_ROOT` mean the then-selected installed data
roots; `MISSION_INPUT` is the canonical approved-scope input, `TRUTH` fresh
default-branch Repository Truth, and `EXPIRY` a UTC instant no more than seven
days ahead. Resolve actual values through the owning installed readback.

```text
engineering-platform-server inspect-assurance-target --data-root "$EP_ROOT" \
  --project-id forge --repository-id forge
forge --data-root "$FORGE_ROOT" server reset preview
engineering-platform-maintenance preview --data-root "$EP_ROOT"
```

If a separate clean-CENTRAL assignment authorizes a reset, follow the exact
`prepare → revalidate → apply → verify → finish` receipts and joint ordering in
[the Forge reset runbook](FORGE_OPERATIONAL_RESET_RUNBOOK.md) and EP's
[CENTRAL operational reset runbook](https://github.com/pcvantol/engineering-platform/blob/main/docs/engineering/EP_CENTRAL_OPERATIONAL_RESET_V1.md);
the preview above performs no reset.
After that operation is terminal, reserve the new Mission's bounded grant and
insert the returned `delegation_id` as its `ep-merge-delegation:` constraint
in `MISSION_INPUT`. The reservation does not activate merge authority.

```text
engineering-platform-server reserve-merge-delegation --data-root "$EP_ROOT" \
  --project-id forge --repository-id forge \
  --merge-role IMPLEMENTATION --merge-role FINALIZATION \
  --merge-role RECONCILIATION --expires-at "$EXPIRY" \
  --assurance-profile repository-autonomous-qs@1
forge --data-root "$FORGE_ROOT" mission inspect --input "$MISSION_INPUT"
forge --data-root "$FORGE_ROOT" mission approve-business --input "$MISSION_INPUT"
forge --data-root "$FORGE_ROOT" mission approve-architecture --input "$MISSION_INPUT"
forge --data-root "$FORGE_ROOT" mission admit --input "$MISSION_INPUT"
engineering-platform-server activate-merge-delegation --data-root "$EP_ROOT" \
  --delegation-id "$DELEGATION_ID" --mission-id "$MISSION_ID" \
  --mission-revision "$MISSION_REVISION"
forge --data-root "$FORGE_ROOT" mission run --mission-id "$MISSION_ID" \
  --repository-truth "$TRUTH"
forge --data-root "$FORGE_ROOT" mission status --mission-id "$MISSION_ID"
```

Use the `mission_id` from `admit` and its approved revision for activation.
Inspection creates no Mission or grant; reservation creates no active grant.
Each later Mission requires its own approval and exact delegation. The
installed target choice is never work approval or execution authority.

MISSION-0017 and the previous Mission-3 acceptance rejection retain their
historical outcomes. This slice does not qualify parallel Actions, automatic
backlog selection, other repositories or other assurance profiles.

`PRODUCTION_CENTRAL_RESET = NIET_UITGEVOERD`;
`PRODUCTION_MISSION_3 = NIET_GESTART`;
`MISSION_0017_OUTCOME = ONGEWIJZIGD`;
`HISTORICAL_MISSION_3_ACCEPTANCE = NIET_GEHAALD_ONGEWIJZIGD`.

## Scoped resource handoff

EP source PR #288, its production release operation and `<EP_UPDATE_A>` are
terminal. The isolated qualification run is terminal; its test grant and
test target selection are revoked. The isolated development service and
all test providers are stopped; protected local evidence is archived for
the owning Architecture lane;
their private identifiers are mapped only in the protected local ledger.
The production EP service remains healthy and active. No production Mission,
reset, provider run, merge grant or follow-on roadmap operation remains
reserved by this delivery.
