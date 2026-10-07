# Scoped worklist hold HTTP producer

Assignment `L3-FORGE-SCOPED-WORKLIST-HOLD-V1-20261007`, plan r37.
JOIN `L3-L4-WORKLIST-HOLD-CAPABILITY-V1-20261007`.
Base protected47c9f406 /2.7.68; selected patch2.7.69. Candidate contract,
not PRODUCER_QUALIFIED until protected exact-main installed qualification.

## Outcome and authority

Owner-provisioned, private bearer grants bind a real existing instance, an
explicit principal and 1..16 existing workset IDs, future expiry at most90days.
Only hold/unhold and scoped command/current readback are authorized. No global
list, owner administration, Mission allocation, cancellation, new approval,
arm/disarm/revoke-workset, membership/order or budget effects.
The installed current operator is revalidated at provision/revoke, every read
and the actual mutation boundary. Actor/role fields in client JSON are rejected.
Status/review/worklist-read grants retain their meanings and cannot command.

The local owner route is `forge-workspace-worklist-control-grant --data-root
<owned-root> issue --principal-id <principal> --workset-id <exact-id>
--expires-at <UTC-time> --token-file <private-output>`; revoke uses `revoke
--grant-id <exact-issued-grant>`. `python -m
forge.workspace_worklist_control_grant` is the equivalent supported route.
Grant/token files use the existing private atomic-write/no-symlink/locked
patterns. No token is returned in a receipt, public fixture or log.

## Versioned contract

Schema: `forge/api/workspace-worklist-control-v1.json`.
GET `/v1/workset-controls/{workset_id}` returns only that exact granted workset,
its verified existing v1 projection, current definition/workset/control
revisions, observed time, held/provenance, and admitted IDs already in that
workset. GET has zero canonical writes, planning, provider, decision, intake
or EP effects.
POST `/v1/workset-controls/{workset_id}/commands` takes the exact request keys:
`contract_version:forge-worklist-control-request/v1`, `operation_id`,
`intent:hold|unhold`, exact `instance_id`, `workset_id`, `definition_revision`
(the existing definition digest), integer `expected_revision`, bounded
`reason_code:USER_REQUEST|TEMPORARY_WAIT`, `hold_operation_id`,
`expected_hold_revision`. For hold, both hold-target fields are null. For unhold,
they identify exactly the previously observed hold operation/control revision.
No caller-supplied actor or role has authority.

Response separates immutable `original_receipt` (`forge-worklist-control-receipt/v1`)
from `current_readback` (`forge-worklist-control-readback/v1`), with actual
principal/grant, exact request digest, original effect revisions/provenance and
admitted Mission IDs. `recorded:false` means exact original operation replay;
it does not promise its old held state is current. GET
`/v1/workset-controls/{workset_id}/commands/{operation_id}` reports PENDING
(execution unknown) or APPLIED and original receipt plus separate current state.
404 means no stored command within this authorized scope; no automatic retry
with a new ID. Revocation/expiry also denies operation readback.

Errors use `forge-worklist-control-error/v1` with bounded codes; unauthenticated
transport uses the existing Forge v1 `AUTHENTICATION_REQUIRED`401 envelope.
403 scope/current-authority denial,409 stale revision/provenance/payload conflict
or busy canonical lease,400 malformed request,503 unavailable canonical source.
Errors do not invent verified principal/current attribution from client data.
Unknown execution is read/reconciled using the original ID/payload.

## Durable command and hold boundary

The existing approved_worksets row retains a bounded64-operation journal.
No second scheduler, workset store, planner or allocator is introduced. Intent
commits before effect under the existing canonical runtime/mutation lease and
private grant-lifecycle lock. Effect plus original receipt commit atomically
in the same row. A process death after intent can be reconciled on the exact
ID/payload only if live authorization/provenance/revision still match. A
conflicting intervening revision stays uncertain/conflicted and has no blind
effect. Exact replay of an applied old hold never undoes a newer unhold.

Hold affects future admission only. Already admitted/active Mission IDs are
truthfully included; no cancellation, EP signal or forced resource release.
Concurrent hold/claim uses the same real canonical leases: whichever is first
wins its boundary, the other sees current revision/busy state. Provenance
records local-owner or exact grant principal, operation and control revision.
Unhold removes only the exact hold owned by that grant principal. An intervening
owner hold, foreign grant, or legacy boolean with unknown provenance cannot be
silently cleared. Legacy worksets remain readable with LEGACY_UNKNOWN hold
provenance; owner controls remain supported. No runtime schema migration is
needed for additive workset fields. History/grants/consumption remain preserved.

Unhold never changes release, decisions, generation, expiry, final acceptance,
evidence, uncertainty or consumed allowance. The existing scheduler rechecks
all those facts afterward. The command runtime composes canonical governance
without provider/host adapters; issuing a control requires no provider login,
Keychain access or EP call.

## Selected qualification and delivery

Actual installed product services, HTTP, private grant auth/current OS operator,
canonical Candidate/governance/workset/runtime/scheduler and stateful EP HTTP
simulator. Only external LLM/OS/repository/EP adapters are deterministic.
Target: protected Forge main, tracked committed exact-source wheel, noneditable
installation outside checkout, version/manifest/source-file matching, selected
matrix, real failure-control, full owning validation/changed production per-file
>80.2%, independent exact-head Quality/Security after convergence, protected
implementation and nonempty normal finalization, final installed/main CI proof.
Existing GP/FCI/serial/read official regression gates remain required.

| Selected boundary | Actual evidence requirement |
| --- | --- |
| Scoped capability | Two principals/worksets, foreign/read-token/routes, same-workset foreign operation denial, provision/revoke/expiry/current operator |
| Durable commands | Same-ID payload conflict, original receipt plus current state, lost HTTP body, fresh process reopen and real SIGKILL after committed intent |
| Hold/unhold | Held future0allocation/provider, active Mission untouched, exact provenance, old replay after unhold, final acceptance remains blocking |
| Canonical serial | Real preapproved A/B, hold/unhold around actual scheduler/admission, final acceptance and finite consumption2, no invented IDs |
| Race | Real separate hold/claim processes; busy/CAS denial or truthful already-admitted receipt, no duplicate intake/provider/EP |
| Read/source failures | Zero GET canonical mutations, malformed/uncertain private store denial with exact disposable fixture restoration |
| CI detection | Genuine revoke of the positive control grant causes the positive replay gate to fail; expected failure proves detection |

L2 independent. L4 graph selection6044025195 remains read-only and pinned to
47c9f406/Forge2.7.68/v1 readschema. This JOIN does not start GUI mutations,
upgrade old grants, switch that graph producer or reopen PR137. Native mutating
consumer is a future separately selected scope. No live EP/personal credentials/
paid provider/operational activation/signing/reset/Mission3/target GitHub writes/
public release/full PRM/IAM family claim or automatic next assignment.
TDE observe workflow success and actual policy assessment remain separate.
Existing ordinary repair/run limits and prior consumed budgets remain intact.
