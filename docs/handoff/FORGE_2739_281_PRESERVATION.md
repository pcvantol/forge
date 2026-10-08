# Exact published 2.7.39 to 2.8.1 preservation maintenance

Assignment: L3-FORGE-239-281-PRESERVATION-V1-20261008, r41.
Join: L1-FORGE-239-281-PRESERVATION-20261008.

This corrects the protected external maintenance controller. It does not rebuild,
replace or modify either published product wheel. The controller is excluded from
the wheel; its protected source revision and complete file SHA-256 are separately
bound. Source NO_BUMP2.10.0 does not select that version for installation.

## Immutable selection

| Binding | Exact value |
| --- | --- |
| Installed version / schema | 2.7.39 / 40 |
| Installed source | ebc43dc12da27353f85c991a26da9852aa790f05 |
| Installed wheel SHA-256 | b62bf5f7a1d937f5224ef941a3dea3e961d28b67d9206fd89b644153aea502f1 |
| Target version / schema | 2.8.1 / 45 |
| Target source | c8833ffa4754800de451cce94b109ef1ad07123f |
| Target wheel SHA-256 | 7e4b6cf2bd4544865ca980ff9c5c0f7e4b104cd9a47f11dc6d1e3e944e1942c0 |
| Original release-complete receipt SHA-256 | 51017bb17faa3d2568e457360d54b873deddbf59eeedb86310b4cb56e1345a76 |

[Published terminal receipt](https://github.com/pcvantol/forge/releases/download/forge-v2.8.1/forge-release-complete-2.8.1-c8833ffa4754800de451cce94b109ef1ad07123f.json)
is consumed unchanged, including its real reconciled publication/cleanup and
installed composition evidence. Historical failed workflows remain historical.
No newer target or adjacent transition is implicitly selected.

## Consumer route

L1 invokes the exact protected `scripts/update_installed_forge.py` with isolated
Python3.14 and the existing full explicit update request. The additional
`--installed-wheel` names the original pinned 2.7.39 wheel. The
`--existing-interpreter` must name its actual virtual-environment interpreter,
not the shared base Python. The updater verifies the complete old product
footprint and package metadata before executing it. Legacy request serialization
and operation digests omit the new field when absent.

Use that same controller with `--assess-only`; retain its exact fresh
`forge-installed-update-assessment/v1` digest, then supply it as
`--assessment-digest`. The immutable historical packaged lifecycle inventory
cannot know this later external maintenance selection and is not its admission
route. This is the existing product-owned external maintenance authority, not
an admin credential, CLI trust override or runtime self-installer.

No project input, registration, choice or provider login is required. Current
runtime/installation, source/wheel, peer-state, controller, interpreter and
resolver bindings must match. Active product processes, writer locks and
nonquiescent runtime state deny mutation. L1 owns authorized service quiescence;
this controller never stops user processes or starts a service.

## Preservation and recovery

The owning target CLI migrates an isolated verified backup through schema40–45.
The exact five new tables are initially empty: `mission_action_slot_snapshots`,
`mission_action_execution_slots`, `mission_action_intent_revisions`,
`approved_worksets`, and `installation_peer_configuration`. Every existing table,
protected metadata value, peer binding and operational-reset state is preserved.
Only declared schema/inventory metadata advances. The source backup is retained
as `forge-schema40.sqlite3` under the original operation.

The existing writer fences, atomic qualified-database replacement, immutable slot,
stable resolver, canonical receipt and current CLI/schema readback are reused.
An interrupted invocation resumes the same request/assessment/operation and exact
bytes. It preserves the original backup/history; no SQL repair, credential export,
new operation, target substitution or budget reset is a recovery route.

## Qualification boundary

The producer matrix uses real published noneditable wheels, project-free original
CLI initialization, genuine canonical history, read-only assessment, actual
migration/activation/readback and replay. Real SIGKILL of owned process groups is
observed at durable STAGED, BACKED_UP, MIGRATION_QUALIFIED and ACTIVATING boundaries;
unhit boundaries are never claimed. Actual writer-lock/process, identity/artifact,
stale-history and old-footprint denials are exercised. A genuinely positive
operation followed by target-file corruption must fail replay independently.

Full owning tests, committed-source qualification, independent whole-slice Quality
and Security, protected implementation/finalization, exact-final-main evidence and
safe cleanup remain delivery gates until actual receipts exist. Producer delivery
does not qualify L1's later real installer continuation. No real user installation,
live EP, project registration, provider login, signing, public artifact replacement,
Mission allocation/start or reset is authorized by this handoff.
