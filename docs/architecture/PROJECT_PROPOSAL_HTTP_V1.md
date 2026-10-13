# Private project proposal HTTP V1

Assignment `L3-PROJECT-PROPOSAL-HTTP-V1-20261013`, R52/plan1.
Forge 2.18.0, runtime schema46 unchanged. Implementation protected-delivered on9736bbbd; finalization and NEW final-main
qualification remain separate gates. This document alone is not installed evidence.

## Producer mapping

| Operation | Route | Authority |
| --- | --- | --- |
| Current support and finite scope | GET `/v1/onboarding/capability` | READ |
| Prepare original proposal | POST `/v1/onboarding/plans` | PREPARE + READ |
| Exact retained proposal | GET `/v1/onboarding/plans/{plan_id}?dossier_id={dossier_id}` | READ |
| Recover known original intent | GET `/v1/onboarding/intents/{operation_id}?dossier_id={dossier_id}` | READ |

All requests authenticate with an owner-issued private proposal bearer capability
and exactly one `X-Forge-Proposal-Audience` matching its audience. Principal,
instance, finite dossier list, permissions, kinds, content transfer and expiry
come from the current private grant. No arbitrary actor/viewer header is trusted.
Legacy read, advisory, worklist and administrator tokens do not authorize these
routes. Proposal tokens cannot authorize existing unrelated routes.

The explicit owner/setup CLI `forge-project-proposal-grant --data-root ROOT`
provides `init`, `issue`, and `revoke`. Init uses an already initialized Forge
instance and actual existing installed operator binding. A dossier is private
proposal storage, not a project, repository attachment, approval or Mission.
Grant issue requires principal, audience, finite dossiers, READ (and optionally
PREPARE), selected kinds, maximum records1..8, expiry up to30days and a new private
token file. Actual tokens and dossier contents never belong in published examples.

## Closed input and frozen output

POST has exactly `contract_version`, `instance_id`, `dossier_id`, `operation_id`,
`proposal_kind`, `input`. Contract is `forge-project-proposal-http/v1`.
Kinds are `pb-render/1.0` and `pb-adoption-preview/1.0`; input is the unchanged
R50 or R51 owning contract. Original supplied uncertainty, exact document bytes,
profile/baseline pins, before/after and diffs are retained. Missing is not ABSENT;
supplied observations are not live EP inspection.

Response contains contract, instance, principal, audience, dossier, operation,
plan ID, kind, original request/record digests and frozen result. Result contains
`state=PROPOSED_NOT_APPROVED`, original contract version, input/result digests,
readable summary and exact artifact path/mode/SHA256/UTF-8 content inventory,
`observations=SUPPLIED_UNVERIFIED`, `repository_quality=NOT_ASSESSED`.
`read_only_result=true`, `approval=NOT_PERFORMED`, `registration=NOT_PERFORMED`.

Same instance/principal/audience/dossier/operation and exact canonical input
returns the same original ID/result. Changed same operation conflicts409.
The client knows operation/dossier before POST; intent GET recovers a lost answer.
GET validates the private retained integrity proof and original binding without
rendering, inspecting, calling providers or upgrading baselines. Separate Server
OS restart preserves original bytes. Store corruption/missing initialized storage
is non-success; setup never silently creates healthy empty recovery state.

## Finite boundaries and publication

Request262144bytes, result1048576bytes, at most64 artifacts/131072bytes each,
8records per dossier maximum,32dossiers,64global records,16MiBstore. Grants at
most32,8dossiers per grant. No server export path or arbitrary download resolver.
Private owned0700 directories and0600 regular files use no-follow descriptor IO,
atomic replacement and fsync; first initialization cannot clobber existing bytes.
A durable initialization witness retains the private record-integrity key.

Rendering holds no authority lock. Commit and each bounded nonblocking socket
send reserve the existing canonical SQLite writer boundary and grant lifecycle
lock, then revalidate current operator/token/audience/dossier/kind. Rendering and
waiting for client writability occur outside both locks. Publication stops on
revocation/expiry/operator change. Bytes already sent cannot be withdrawn; a
partial interrupted JSON body is not a new successful response. Publication is
bounded to5seconds. Lock order is proposal grant then canonical database.

401 denotes invalid current credential;403 denied scope;409 changed intent or
capacity;422 unsupported owning input;503 unavailable/corrupt proposal storage.
No raw supplied content, host path or credential is returned in error messages.
Capability is authenticated current support, not approval or execution readiness.
Decisions/apply/project registration remain unavailable.

## Synthetic peer example

Use only existing synthetic `examples/project-bootstrap/authority-input.json`
and `examples/project-adoption/adopt-existing-vision-input.json` as the `input`.
Set dossier `synthetic-product-a`, operation `synthetic-prepare-1`, instance to
actual capability readback, audience to the explicitly issued test audience.
Prepare, recover via intent, then read the returned plan ID. Repeat exact POST;
change supplied purpose under the same operation and expect409. A different
caller's dossier cannot read this plan. No actual bearer value is published.

This binds HOB-F02 prepare/read and original intent recovery, only the selected
PB-F7 adapter subset. HOB decisions, apply, repository effects, EP inspection,
full onboarding, native Workspace and execution remain separate open ownership.
L2/L4 assignments and producer pins are unchanged; their ACK is not a gate.

## Protected delivery and finalization

Implementation [PR287](https://github.com/pcvantol/forge/pull/287) merged on
`9736bbbd96d451f9035dbf8a988a2ec4f85331e8`; exact reviewed sourcee182,
full owningCI38432837870,1551tests and all changed source coverage strictly>80.2%.
The [delivery record](../qualification/R52_PROJECT_PROPOSAL_HTTP_DELIVERY_2026_10_13.md)
binds current authority/storage/publication repairs, independent Quality/Security,
real Mac and labeled hosted installedHTTP proofs, original failures/counters,
peer contracts and future final-main qualification. Finalization is NO_BUMP.

NEW exact-final-main installedHTTP/OSrestart/readback/cleanup must follow this
nonempty independently reviewed protected finalization. Owning terminal #207
register closes only the selected subset after actual fresh proof and current
requiredCI PASS; no full PB-F7/HOBdecisions/apply/EP/native acceptance claim.
