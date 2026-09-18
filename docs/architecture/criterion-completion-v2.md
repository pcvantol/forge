# Criterion-bound Mission completion v2

This contract defines Forge's interpretation of Mission evidence. It is not a
release receipt, installed-host qualification or approval to start a Mission.
Forge owns assessment and subsequent Action derivation. The Execution Host
owns execution, terminal receipts and its repository delivery claims.

## Approved assessment boundary

Architecture approves one `CriterionAssessmentContract` for each exact Mission
acceptance criterion. All requirements in a contract are conjunctive: every
requirement must be proven. The approved planning envelope binds these
contracts, their validity policies, the repository source, `maximum_actions`
and `maximum_consecutive_no_progress_actions`; Mission Intake checks the same
values against the Mission. Runtime planning cannot add or reinterpret them.

The implemented `repository_json` requirement names a safe relative artifact
path, a JSON pointer and an explicit canonical JSON expected value. Forge
observes the bytes at the exact accepted delivery revision and compares that
selected JSON value with the approved expectation. An empty pointer selects
the whole document. Duplicate object keys, non-finite values, malformed JSON,
absent pointers and mismatches cannot pass. This proves the approved
structural repository property only: a JSON field asserting that a test passed
does not establish that the test executed or that runtime behavior is correct.

For example, an approved predicate for `config/runtime.json`, `/state/source`
and the JSON string `"durable-state"` establishes that exact configuration
value at the observed revision. It cannot establish a live service's durable
behavior. Broad natural-language criteria need appropriate approved predicates
or a separately supported authoritative evidence source; a planner's intended
change and an agent-authored PASS statement supply neither.

`host_control` requirements retain an exact control identity and command as
approved intent. The current supported producer evidence does not independently
establish command execution. Such a requirement is `UNSATISFIED` with
`UNSUPPORTED_AUTHORITATIVE_EVIDENCE_SOURCE`. If all remaining requirements
have this limitation, continuation blocks before another provider call.

## Observation and provenance

The normal repository reader is read-only HTTPS to the fixed public GitHub raw
content origin. Architecture supplies an exact owner/repository and the
installed repository identity must match. Reads require a lowercase 40-character
commit revision, reject redirects, have a 15-second timeout and a 1 MiB byte
limit per artifact. The reader does not discover credentials, accept arbitrary
URLs, execute repository code or use a local checkout as evidence. Private or
unavailable artifacts remain explicitly unavailable through this reader.

Each observation binds the approved Mission digest, criterion identity,
contract and requirement digests, pointer, source repository, artifact path and
content digest to the canonical Action, receipt, report and delivered repository
revision. Candidate revision, when provided by the host contract, stays a
separate provenance field. Forge does not reinterpret it as the delivered
revision or fabricate missing provenance.

The evaluator requires canonical accepted COMPLETE receipts and exact
observation joins. COMPLETE proves the Action's host outcome; it does not prove
every Mission criterion. Conflicting immutable observations fail closed.
Repository Truth alone, receipt associations, provider prose and expected
evidence are not criterion observations.

## Current properties and historical delivery

`current_revision` is the default. Every required predicate must have passing
evidence at the current Repository Truth revision. A previous PASS is retained
as history but cannot be copied onto a newer revision. A later failure or an
unavailable current observation leaves the criterion unproven. A new Action
can re-observe retained and newly delivered properties at its actual revision.

`historical_delivery` must be explicitly approved. A passing observation of a
past delivery may continue to establish that historical event even if a later
revision lacks the property. It never establishes current behavior. Multiple
Actions can contribute different required facts under this policy; they retain
their original Action, revision and receipt provenance. Conflicting facts for
one immutable source revision do not become valid by selecting an older PASS.

Completion requires every approved criterion to be proven and no unresolved
materialized required Action. The runner first persists each Action outcome,
Repository Truth, observations and deterministic assessment. Partial results
remain partial and trigger bounded planning when supported progress is possible.

## Planning, limits and replay

The persisted planning snapshot includes approved bounds, criterion and
requirement results with reasons, observation provenance, prior Actions and
their contributions, exact terminal receipt summaries and current Repository
Truth. Observed JSON values are excluded from the provider context. Matching
accepted verified delegation summaries remain separate from host receipts and
never become criterion proof. Restart uses the same durable context and result
identity rather than reconstructing authority from conversation or provider text.

Progress is a newly proven approved requirement identity, scoped by criterion,
contract and requirement digests. A new receipt, plan or hash for the same
already proven requirement is not progress. Re-proving a requirement after its
actual invalidation is progress. Consecutive assessments with no new fulfilled
requirement are bounded by the approved no-progress limit; the total Action
limit independently bounds continuation. No limit increases autonomously.

Successor work is also checked against prior normalized objective, scope,
writes, expected evidence and validation strategy, excluding logical Action ID
and provenance. Renaming identical work does not evade this check. It is not a
general semantic-equivalence oracle; finite approved ceilings also bound
paraphrases. Unsupported evidence, exhausted limits and duplicate work produce
explicit blocked reasons.

An atomic continuation marker binds the persisted terminal evidence,
assessment, Repository Truth and Mission. Restart after assessment resumes that
decision without fetching or assessing the same terminal result again. The
successor's materialization and durable derivation acknowledgement share one
transaction; replay before it reuses the durable provider result and replay
after it does not allocate another successor. Materialization failures remain
recorded. Existing policy pauses follow this sequence and consume one approval
at their existing boundary; the correction grants no automatic retry authority.

## Compatibility, storage and qualification

Completion schema 1.0 receipt associations remain readable historical data;
they cannot satisfy v2 predicates. Missions without approved assessment
contracts remain readable, but assessment reports
`APPROVED_ASSESSMENT_CONTRACT_MISSING` and dynamic successor derivation blocks
with `LEGACY_ASSESSMENT_CONTRACT_MISSING`. The runtime does not invent an
approval or reopen a historical terminal Mission to upgrade its outcome.
The old five-seed bootstrap sequence similarly preserves already persisted
terminal qualification readback, but refuses fresh or partial legacy execution
before approval creation or any host call. Its former blanket `complete`
criterion cannot supply substantive qualification.

Runtime schema 39 is a reader compatibility fence for the changed completion
meaning. Migration from 38 changes metadata only; historical Mission,
allocation, approval, receipt, maintenance and authority rows are preserved.
Older schema-38 binaries reject the future schema. `completion_history` and
continuation markers reside inside the existing `mission_state` document.
There are no new application tables or standalone purge rules. Their reset
classification remains operational Mission history under the existing owning
[reset contract](FORGE_OPERATIONAL_RESET_V1.md); migration and installation do
not reset or purge it.

Generic observer/evaluator and injected loop tests establish their stated
source-level properties. Normal installed composition qualification must run
the production factory, collector, evaluator, planner and state store from the
exact non-editable artifact, substituting only explicit external boundaries.
The [baseline regression](../operations/CRITERION_COMPLETION_BASELINE_REGRESSION.md)
records the old defect separately. Passing source tests, an artifact harness,
release publication and installed activation are distinct evidence claims.
