# Supplied-inventory project adoption preview

Assignment `L3-PROJECT-ADOPTION-PREVIEW-V1-20261013`, R51.
This delivers the portable PB-F2 inspect-input/preview subset. Actual inspection,
identity registration, frozen approved execution plans, decisions, HTTP/apply,
EP effects and readiness remain separately selected work.

## Real user outcome and commands

Supply a finite source-bound document inventory and an explicitly selected
[R50 portable profile](PROJECT_BOOTSTRAP_PORTABLE_RENDER_V1.md). Forge proposes
what to keep, which supplied existing document to link, which additions or
content changes to discuss, and which conflicts or missing facts remain open.
No repository is scanned, fetched or changed.

```sh
forge-project-adoption validate-input --input supplied-packet.json
forge-project-adoption preview --input supplied-packet.json
forge-project-adoption preview --input supplied-packet.json --export new-private-proposal
forge-project-adoption check-proposal --proposal new-private-proposal
```

The terminal and README present paths, source status, before/after hashes,
mapping-only choices and open decisions. Exact UTF-8 document content and diffs
remain exclusively in the private frozen input and proposal.json. They are
untrusted data, never shell/model/agent instructions. Inspect them using a trusted
private viewer; do not publish real document packages or execute their scripts.
Public repository examples contain exclusively synthetic content.

The export is exactly `preview-input.json`, `proposal.json` and `README.md`, with
0700 owned root and 0644 file modes. New directory only; no overwrite or merge.
Parents are descriptor-walked without symlinks, existing Git ancestors reject,
and final `.git`/case aliases reject. A non-sticky shared writable parent rejects;
the opened root must still be owned and0700 before writing any payload. Reopening
checks the private root, finite inventory, all bytes and modes against the trusted
installed service. Interrupted exports are partial and never accepted/reused.
Inputs, old proposals, unrelated files and disposable target evidence stay intact.

## Closed source contract and typed observations

Packaged contracts are `forge/project_adoption/assets/input.schema.json` and
`proposal.schema.json`; independently pinned by this service. Contract
`pb-adoption-preview/1.0`, inventory `supplied-document-inventory/1.0`.
Nested `bootstrap_input` retains the exact R50 input contract; no old catalog,
renderer, baseline assets, profile pins or portable render check is changed.
The shared finite safe export is reused; adoption plans use their own validation.

An input binds:

- One supplied repository/revision/reference and an explicitly declared current
  revision reference; all are `SUPPLIED_OBSERVATION / SUPPLIED_UNVERIFIED`.
  Even equal revision strings are not actual current HEAD proof.
- Inventory digest over canonical complete inventory, covered/excluded paths,
  worktree context and finite document observations.
- `PRESENT` with SHA256/mode and optionally actual UTF-8 content; `ABSENT`,
  `UNKNOWN`, `REFUSED` and `NOT_EXAMINED` with no invented bytes or hashes.
- Explicit requested R50 artifact paths and optional mapping choices. Selection
  or a semantic hint is not approval or independently verified equivalence.

Not listed is always UNKNOWN, including in a `COMPLETE_SUPPLIED` inventory.
Additions require an explicit ABSENT observation for the exact covered,
nonexcluded path. Excluded/uncovered paths and missing needed content remain
insufficient. PRESENT hashes without bytes cannot establish content comparisons.
A known present B8R declaration without bytes keeps identity comparison open
for the whole proposal. A known conflicting identity blocks all selected
proposals, even when only ordinary documents were requested.

Provided owner labels and hashes do not qualify inspection, consent, source
freshness or a real project identity. A stale declared revision is a conflict.
Dirty/staged/untracked/ignored context is preserved, never committed or cleaned;
ABSENT versus a context-present path is a conflict. Source/control/secret paths
such as case-fold `.git`, `.env`, `.aws`, `.ssh`, `.codex`, terminal controls,
absolute/traversal paths and aliases reject before output. Unsupported physical
hostpaths or arbitrary owner wire payloads are not normalized into identities.

Finite limits:131072-byte input/output files,32 supplied document entries,
20 requested artifacts,64 coverage/exclusion paths,8192 content characters and
16384 UTF-8 bytes per supplied document. Each proposal uses at most20 entries.
Huge packages return typed unsupported/invalid before export. No external
schema resolver, include, URL fetch or directory crawler exists.

## Proposal semantics and document preservation

`PROPOSED_NOT_APPROVED` is the only prepared state. Trusted check returns
`VALIDATED_PREVIEW_NOT_APPROVED`, never approved/applied/adopted or ready.

| Operation | Exact meaning |
| --- | --- |
| KEEP | Supplied target content retained; matching or differing template content grants no replacement |
| LINK_EXISTING | Explicit mapping-only; target before remains distinct, mapped source has its own byte binding; no target-after bytes or second vision |
| PROPOSE_ADDITION | Exact covered ABSENT target plus appropriate R50 proposal bytes, hashes and owner/update metadata |
| PROPOSE_CHANGE | Explicit same-path replacement proposal with actual target before/after/diff; known PROJECT_OWNED/source owner required |
| CONFLICT | Identity, stale state, duplicate/ambiguous document, target/source mismatch, protected pin/projection or contradictory evidence |
| INSUFFICIENT_INFORMATION | Unknown/unexamined/refused/omitted/excluded paths, missing necessary bytes or document references |

Cross-path replacement is unsupported rather than inventing the target's before
state from a different document. Different canonical and mapped source documents
are a conflict. Existing baseline pins, derived projections and append-only
records cannot be replaced by this preview. Unknown ownership/update class stays
open. A child cannot request a second vision/roadmap from an authority profile.
Existing Dutch or other UTF-8 documents retain exact original bytes and language.
New R50 document proposals are English only; there is no silent translation.

The R50 no-product-code validation document/project contract and exact-new-tree
validator/workflow are inappropriate adoption templates for an existing codebase;
requests to add/replace those remain conflict, not fake quality or missing-tool
PASS. README/BOOTSTRAP/AGENTS references require actual covered supplied existing
script/contract/doc bytes. Even then their commands/contracts are NOT_EXECUTED /
NOT_QUALIFIED. Repository build/test/security quality is always NOT_ASSESSED.
No ordinary template validation becomes a technical baseline or architecture scan.

Proposal digest excludes its own digest field and binds the whole canonical
plan; input/inventory digests, original source vector, unchanged R50 catalog and
render digest are separately included. Changed product input, mapping/source
vector or baseline changes content binding. Old exports are never overwritten.
The future approval must bind the exact proposal; this slice creates none.

## Concrete examples and producer joins

[Existing Dutch vision](../../examples/project-adoption/adopt-existing-vision-input.json)
links `docs/RICHTING.md` to the vision artifact and retains original language;
[proposal](../../examples/project-adoption/adopt-existing-vision-proposal.json)
and [readable summary](../../examples/project-adoption/adopt-existing-vision-README.md)
show mapping-only, no target-after and an appropriate architecture addition.
[Identity conflict](../../examples/project-adoption/identity-conflict-input.json),
[full plan](../../examples/project-adoption/identity-conflict-proposal.json) and
[summary](../../examples/project-adoption/identity-conflict-README.md) show real
blocking conflicts with no proposed new content. All bytes are synthetic.

B8R `.engineering-platform/repository.json` remains fixed, schema1.0 and its
existing project/repository identities, authority relationship and validation
shape are not extended. Forge reads supplied bytes only. It neither registers
IDs nor claims an accepted EP inspector/attachment grant.

HOB-F02 PlanProposalRequest/FrozenPlan are future owner HTTP adapter concepts;
this real `forge.project_adoption.service` is the reusable implementation for
its separately selected input mapping. HOB-EP02 remains the proposed owner
inspection/assessment authority. This intake is not their published wire schema,
missing runtime or permission fallback. HOB source observations are not consumer
pins. L2/L4 received concrete closed contracts and full synthetic input/output;
their ACK, full EP inspection and implementation are not gates. Existing tasks,
producer pins, testdata and budgets remain unchanged.

## Qualification and closure boundaries

Scoped mapping: portable supplied-input portions of PB-05/10/11/14/22 and
relevant deterministic/offline/role/no-Mission parts PB-12/13/15/17/18/31/32/36/39/40.
No full family or repository-adoption/readiness closure is claimed.

Small semantic tests cover unknown/ABSENT, aliases/mappings/identity/source
context, actual before/after, preservation, code-claim guards and private export.
Installed qualification uses a real noneditable wheel, full committed source/
wheel/installed inventory and entrypoint binding, real CLI plus independently
source/network/command-guarded entrypoint workers. Direct and descriptor source
probes and a socket probe fail before each worker; synthetic observations are
never called live EP evidence. Independent processes/cwd/hashseed/environment
replay, old export/pin preservation, semantic checks and coherently rehashed
unknown-as-absence tampering control are actual required cases.

Normal CI uses that installed matrix with bounded private child logs and only
closed synthetic public receipt uploads, retaining original failures before
owned cleanup. New exact-final-main evidence follows protected source delivery,
complete independent Quality/Security and nonempty reviewed finalization. R50 is
already closed under its own original source/artifact/register bindings, which
remain unchanged. Source tests are not installed qualification, and no pending
R51 stage is recorded as completed. No automatic following feature, public
release, signing, live EP/Workspace or user-data migration is authorized.


## Protected implementation and finalization

[Delivery record](../qualification/R51_PROJECT_ADOPTION_DELIVERY_2026_10_13.md)
binds PR285/protected implementation eb717036, complete independent reviews,
actual hosted1533-test/31-case installed evidence, exact source/tree/artifact
and preserved failures. R51 finalization and NEW exact-final-main installed
readback remain open until their own gates pass and the external register
records terminal closure. This does not close full PB-F2 or peer execution.
