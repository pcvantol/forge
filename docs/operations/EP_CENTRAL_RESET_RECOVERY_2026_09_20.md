# EP CENTRAL reset recovery — 20 September 2026

RESET_RECOVERY_ACCEPTANCE = GEHAALD

The interrupted joint Forge/Engineering Platform CENTRAL reset was completed using its **existing** operations. The prior production Mission 3 acceptance attempt remains `NIET_GEHAALD`; it ended before T0, and no Mission was started during this recovery.

## Cause and correction

EP 2.3.89 reached `ARTIFACTS_ARCHIVED` and then attempted to delete operational rows in `engineering_metadata` while that table's maintenance writer-block trigger remained installed. SQLite rejected the delete with `EP_OPERATIONAL_MAINTENANCE_ACTIVE`; the database transaction rolled back and the durable operation stayed at `ARTIFACTS_ARCHIVED` with generation 0. An isolated fixture using the installed 2.3.89 code reproduced the same failure.

[EP PR #289](https://github.com/pcvantol/engineering-platform/pull/289) includes `engineering_metadata` in the triggers dropped and restored inside the one apply transaction. It also recognizes only the exact published 2.3.89 implementation binding for a pre-existing `ARTIFACTS_ARCHIVED` operation. The ordinary operation, authorization, backup, identity, schema, source, writer-fence and generation checks still apply. The protected merge is `0ae422c96bcfa18ed56417779d6b216d9ca27809`.

[Engineering Platform 2.3.90](https://github.com/pcvantol/engineering-platform/releases/tag/engineering-platform-v2.3.90) was qualified and published. The PyPI wheel SHA-256 is `6b84b934eb93d0af560de46fec7309a28de52f4ead5e7ed4fa7d875aef6a431a`; the sdist SHA-256 is `509e3e369eb92c4383872a72dbee94daea2cd4b3463e3306056000513eaa8054`. The full EP repository suite passed (2,016 tests; 2 skipped), and independent Quality and Security reviews passed.

## Qualification and production timeline

| Stage | Result |
| --- | --- |
| Failure | Existing Forge operation `APPLIED`/generation 1; existing EP operation `ARTIFACTS_ARCHIVED`/generation 0; joint operation pending. |
| Isolated restart | Installed 2.3.89 reproduced the trigger abort. A new process with the final registry wheel rejected wrong operation and plan bindings, resumed the original fixture operation to `VERIFIED`/generation 1, and kept generation 1 on repeated continuation. |
| Joint fixture | Real installed Forge and EP reset CLIs reproduced the partial state; the final registry wheel resumed EP, and the original joint coordinator completed reconcile, verify, authorize-resume and both finishes. Both fixture generations were 1. |
| Production preparation | The owning updater prepared and verified the exact published 2.3.90 wheel without starting the fenced EP service. |
| Production continuation | The same EP reset operation advanced to `VERIFIED`/generation 1. The joint coordinator reached `BOTH_VERIFIED`, authorized resume, finished EP while its service was stopped, then finished Forge. Joint state: `COMPLETE`. Forge apply was not repeated. |
| Service and installation | The owning service route reopened EP after joint finish. The already prepared updater candidate was then admitted and activated through the normal updater. Update state: `COMPLETE`; EP health and readiness: PASS. |

No second Forge or EP reset operation was created. Original backups, reset receipts, fences, dataset generations and historical failure evidence were preserved. The fences were consumed only by the owning finish transitions.

## Clean baseline and handoff

Forge 2.7.26/schema 39 and EP 2.3.90/schema 72 both report generation 1. Integrity and foreign-key checks pass. Forge has no Mission, Action, planner or queued execution state. EP has no submissions, runs, provider invocations, leases or run-bound telemetry. There is no active Mission delegation and no historical re-ingest. Forge's authenticated EP peer preflight is PASS; the repository-bound assurance target for `pcvantol/forge` is ready under the effective protected-PR policy.

Normal service reopening created new EP component logs and one maintenance-attempt metadata record **after** joint finish. They are service activity from the new generation, not restored historical Mission or run evidence. They are disclosed here so the next acceptance kickoff can confirm that no Mission-specific execution population has appeared since this baseline.

The EP release and installation update operations are complete. No Mission controller, reset continuation, update or release process remains active. EP is healthy, both reset fences are inactive, and this recovery releases its Forge, EP and repository resource holds for a separately authorized acceptance attempt. That attempt must use a new T0 and fresh Mission-bound delegation; it must not repeat this reset solely to obtain a visually empty database.

AUTONOMY_E2E_ACCEPTANCE = NIET_GEHAALD_ONGEWIJZIGD_VOOR_DE_AFGEBROKEN_POGING  
MISSION_EXECUTION_STATE = NIET_GESTART  
NEW_MISSION_STARTED = NEE  
PRODUCTION_MISSION_3 = NIET_GESTART
