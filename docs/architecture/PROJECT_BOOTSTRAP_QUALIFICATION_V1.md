# Project bootstrap V1 — shared qualification catalogue

**Status:** PLANNED qualification. Owner-requested documentary contract; NO_BUMP.
The Forge [bootstrap design](PROJECT_BOOTSTRAP_AND_ARTIFACT_MANIFEST_V1.md) owns project semantics. EP and Workspace implement/qualify their own companion responsibilities. A row is a required scenario family, not a claim a test ran. Suites bind exact package/source identities and report actor, plan/operation, target, expected/actual evidence and untouched resources.

| ID | Scenario | Required proof |
| --- | --- | --- |
| PB-01 | Runtime initialization versus project bootstrap | `server init` has no target-repo/project/Mission effects; data-root never means target checkout |
| PB-02 | Genesis missing/empty directory | Qualified local Git foundation and actual files; no remote request or implicit Mission |
| PB-03 | Genesis unborn Git | Stable identity across first commit; no invented predecessor SHA |
| PB-04 | Genesis existing clean repo | Preserve ancestry and unrelated content; approved additions only |
| PB-05 | Dirty/staged/untracked/ignored content | Inventory/preserve or explicit block; never silently commit/stash/delete |
| PB-06 | Genesis with existing remote | Explicit classification; no network/push caused by bootstrap |
| PB-07 | Managed absent remote | Exact approved namespace/visibility/resource birth, seed readback, subsequent protection |
| PB-08 | Managed unborn remote | No fabricated PR; conditional absent-ref creation only under valid birth authority |
| PB-09 | Managed existing README/history | Adoption PR, original history/policy preserved |
| PB-10 | Existing matching project | Idempotent attach/reconcile; no duplicate IDs, repo or grants |
| PB-11 | Drift or conflicting project identities | Exact conflict explanation; no reassignment or best-match guess |
| PB-12 | Artifact profile selection | All required/common artifacts and only selected conditional assets; finite file manifest |
| PB-13 | Deterministic render/replay | Same approved input and templates yield same bytes/digests; no dynamic post-approval regeneration |
| PB-14 | Modified project-owned/generated files | Expected-hash guards and adoption diff; no destructive overwrite |
| PB-15 | Template/baseline tampering | Hash/version/compatibility/license checks fail before execution |
| PB-16 | Path/symlink/case/nested-repo attack | No outside-target write, .git injection or confused common-worktree ownership |
| PB-17 | Untrusted repository instructions/hooks | No authority escalation or implicit script/hook execution |
| PB-18 | Installed source independence | Genesis baseline rendering/local checks without Forge/EP/source-contract checkouts or remote schema fetch |
| PB-19 | Managed remote capability unavailable | Required control remains blocked/incompatible, not omitted or changed to Genesis |
| PB-20 | Host governance readback | Actual rules/checks/ownership match current desired state; API success alone insufficient |
| PB-21 | New CI check bootstrapping | Existing required contexts demonstrable; no circular missing-check PASS or protection bypass |
| PB-22 | Authority and policy separation | Peer credential/template/profile never creates provisioning or Mission authority |
| PB-23 | Duplicate/concurrent requests | One accepted operation/resource; different bytes under same idempotency identity conflict |
| PB-24 | Lost response/crash at each effect | Same operation readback; no duplicate creation, force-push or unnoticed mixed state |
| PB-25 | Cancellation/partial failure | Exact effect inventory; retained evidence; destructive compensation separately authorized |
| PB-26 | Promotion to absent remote | Preserved IDs and complete approved ancestry; separate remote governance proof |
| PB-27 | Promotion to existing compatible/divergent remote | Fast-forward/identity verified or explicit block; no unrelated-history merge/force push |
| PB-28 | Promotion publication safety | All approved refs/history inspected; secrets/license/visibility gates before disclosure |
| PB-29 | Promotion interrupted after push | Disclosure remains visible; Managed activation withheld; no simultaneous mixed-mode writers |
| PB-30 | Relocation/fork/second installation | Stable attach versus explicitly new identity distinguished; no adoption of grants from Git |
| PB-31 | Multi-repository project | One authority, independent child IDs/results; partial target cannot become ready; no atomicity claim |
| PB-32 | CLI/HTTP parity and peer boundary | Same owning decisions/receipts; Workspace and Forge never peer-shell/import/query other DB |
| PB-33 | Workspace draft/preview/approval | Exact mode, files/settings diff and role-bound consent; edits invalidate stale decisions |
| PB-34 | Workspace freshness/reopen/errors | Resume same operation, partial results/owner shown; selected card or optimistic UI is no authority |
| PB-35 | Accessibility/locales | Keyboard, screen reader, desktop/mobile and en/nl/de/fr/es; identifiers never translated |
| PB-36 | No hidden first Mission | Ready project proposes only; separate Candidate/Business/Architecture/release decisions remain |
| PB-37 | Roadmap authority/projection | Empty draft allowed, no fake done/canonical Mission IDs; changes remain source- and decision-bound |
| PB-38 | Reporting/export/telemetry | Consistent scope/snapshot and exact operation IDs; bootstrap costs not miscounted as Mission execution |
| PB-39 | Baseline upgrade/adoption | Pinned old contract stays valid until governed adoption; historical Action snapshots unchanged |
| PB-40 | Zero-production/stack-specific validation | No fake 100% coverage or green missing tools; capability-appropriate local/CI validators |

## Qualification layers

Documentary validation checks inventory uniqueness/conditions, schema syntax, references and acyclic dependency graphs; it does not qualify bootstrap runtime behavior. Deterministic application tests use synthetic stores and explicit external fixtures. Installed integration tests use real own services, local Git/filesystem and actual HTTP boundaries. Managed qualification additionally uses a separately authorized repository-host test resource and real provider readback; Genesis proves zero remote calls. Test resource retention/deletion is separately authorized.

Qualification canaries must not use personal production repos/data as disposable fixtures. Evidence redacts secrets and raw host paths where not necessary, preserves unsupported outcomes, and never manufactures reviewer/owner approvals. Forge project-semantic tests do not depend on completion of Workspace UI. No PB node is added ahead of the current Mission-3 canary.
