# Adaptive Action sizing and decomposition V1

**Increment:** `ADAPTIVE_ACTION_SIZING_V1`. **Owner:** Forge planning/policy.
**Status:** PLANNED implementation; design only, NO_BUMP. No live activation.
[Delivery DAG](../roadmap/adaptive-action-sizing-v1.json) refines the existing
AI Mission Planner, Living Mission Graph and POL-F/POL-B, not a new scheduler.
Peer contracts: EP `docs/engineering/ACTION_EXECUTION_ENVELOPE_V1.md` and
Workspace `docs/ADAPTIVE_ACTION_SIZING_V1.md`. Each repository owns its delivery.

## Evidence and scope

Source pins: Forge `8db69baf802a38526cffa34ff9407ce5eb5a1cd0`,
EP `fc250a55ad2433b0e596189fa4c8d260dac6bc77`,
Workspace `f7c64ea2ca2916bdbe60933bcc30ce405f9dfb3b` (2026-09-12).
In `forge/runtime/dynamic_mission.py`, `_OneActionProvider` restricts the serial
composition to ONE proposed Action per invocation, not its size. In
`forge/planner/action_derivation.py`, AIMissionPlanner derives, validates and
materializes. DerivationPolicy constrains scope/gates/risk, not execution size.
`forge/provider_security.py` has planning token bounds; those do not prove an
EP execution/review budget. EP's SA-ROLE/RMP model allocation is a planned join.
These are source observations, not installed or live capability claims.

Three decompositions remain distinct: Business/Architecture refine project goals
into approved Missions; Forge plans coherent Actions inside one Mission; EP
executes each Action through steps, tool calls, validation, independent reviews
and bounded repairs. One Action is not one model response. A mega-Mission with
independent outcomes should be refined before approval, but size alone need not
force a new Mission. Never split a committed Mission to escape scope or budgets.

## Policy and decisions

Name the user preference **Increment size**, not ambiguous breakdown aggression:
`SMALLER`, `BALANCED_ADAPTIVE`, `LARGER_COHERENT`. BALANCED_ADAPTIVE is the
proposed default for new qualified configurations, not a live default change.
All three remain adaptive. Project defaults and permitted Mission overrides use
existing versioned policy/assignment/activation services. Provider/model/effort
selection remains separate. No preset changes reviews, authority, effect modes,
repair ceilings, hard deadlines, account/billing, or runtime concurrency limits.

Policy declares bounded thresholds, estimator version and confidence handling:
coherence, dependency/repository boundaries, uncertainty/risk, required context,
expected session growth, review load, safe intermediate state, and whole-cycle
cost. No universal file/LOC/token cutoff, percentage of context or size multiplier
for high reasoning is approved here. Unknown hard capability is not unlimited;
unknown estimates require a qualified conservative policy or a visible block.
Every numeric UI control later needs a supported unit/range/enforcement source.

Optimize expected planning/setup + implementation + validation/review + rework +
handoff/integration burden SUBJECT TO quality/safety floors. Estimates are not
optimality proof. Prefer coherent independently verifiable outcomes, bundling
necessary tests/docs with implementation. Split at meaningful contracts, risk or
repository boundaries; do not create one Action per file/class/test. A small
security change can require finer control than a large mechanical doc update.
One repository per Action is the existing V1 target; this adds no multi-repo
execution or parallel permission. Dependency order is not resource scheduling.

## Planning placement and bounded negotiation

1. Load exact approved Mission, remaining criteria, current evidence, policy and
   scoped EP execution-envelope observation. Forge's planner model is not EP's
   implementer or reviewers; do not infer their capacity from it.
2. Maintain a coarse rolling horizon; derive only the next eligible coherent
   increment in the current serial composition. First Action and successors
   both require explicit contribution to unmet approved criteria or a supported
   Mission-caused blocker. A useful uncertainty-reduction result may be a first
   assessment/design Action; it is not a mandatory preliminary ritual.
3. Produce an untrusted size assessment with included/excluded work, dependencies,
   artifacts/criteria, required read/write effects, estimates and confidence.
   Deterministic checks enforce measurable bounds and applicability; semantic
   uncertainty is not made certain merely by a model calling its task small.
4. Evaluate locally and obtain the qualified EP non-generating fit assessment.
   An optional missing endpoint is not invented: use a qualified profile-based
   static fit route only if it proves all required inputs, otherwise unsupported.
   Outcomes distinguish FIT, TOO_LARGE, UNSUPPORTED, STALE and UNDETERMINED;
   these are target vocabulary, not existing v1.2 enums. EP reports limits and
   reasons; it never creates the replacement Action/dependency graph.
5. Before materialization, bounded re-derivation can split too-large work or
   coalesce unnecessary fragments. Each generation consumes its planning allowance.
   Do not implement a hidden unlimited negotiation loop. A necessary unsplittable
   change needs an already permitted qualified profile or an explicit decision.
6. Freeze Action semantics, sizing decision and profile/envelope references;
   submit via HTTP. EP rechecks the actual candidate/context/profile at admission
   and each relevant phase. Fit is neither admission nor reservation/authority.
   Stale profile or fallback outside the proven range cannot silently proceed.
7. Reconcile real evidence and update the UNMATERIALIZED remainder. Never mutate
   a dispatched Action to squeeze in work or reinterpret a partial result as PASS.

Logical `ActionSizingDecision` binds Mission/revision, planning snapshot, unmet
criteria, proposed Action semantic digest, effect/repository boundaries, policy/
estimator, EP instance/profile-set/envelope revisions, per-phase estimates and
observation coverage, fit outcome, alternatives/reasons and history. Persist
bounded rationale, not private reasoning or raw secrets. Actual accepted EP
profile/request identity must reconcile to the planned constraints.

## Context, reasoning, work budget and review feasibility

For EACH relevant implementation/review/repair call assess required system/tool/
role instructions + relevant evidence/source context + retained session/tool
history + reserved generation/reasoning space + safety headroom against that
profile's effective context. Adapter-defined accounting prevents double-counting
reasoning already included in an output limit. Output-per-call and accumulated
Action tokens/time/turns are separate. A short prompt may describe huge work;
large context or compaction is not proof of cognitive or review feasibility.
Tool reads and diff/artifact growth can change estimates; EP must detect actual
overflow before the affected call and use only qualified recovery/compaction.
Never truncate mandatory contracts, safety criteria or review scope to fit.

Every REQUIRED reviewer must receive and evaluate the complete applicable change.
Its context, output, tooling, rubric and qualified capability constrain the Action
as well as the implementer. Advisory roles cannot silently become the bottleneck
or replace mandatory reviews. Effort/speed are provider-specific settings and
measured characteristics, not universal scales or permission for more scope.
No declared hard token/cost ceiling without an enforceable adapter boundary;
requested, estimated, enforced and observed values remain distinguishable.

## Feedback without scope drift or budget laundering

Record predicted/observed context and usage by phase, latency, first-pass criteria,
review defects, repairs, handoff costs and evidence coverage. Classify credential,
route, storage, sandbox and provider failures separately from actual size/context/
complexity failures. Do not shrink tasks automatically after unrelated outages.
V1 adapts within the pinned policy; changing thresholds/defaults is a governed
proposal, not an online learner silently editing policy. Prevent oscillating
split/merge and endless tiny progress with finite planning/progression allowances.
No lower-bound target may force unnecessary work or prevent early completion.

A pre-execution rejection can be replanned only with proof no work was accepted;
a lost POST, timeout or MAY_HAVE_HAPPENED first requires exact-lineage recovery.
Decomposed corrective work keeps original failure/repair ancestry and remaining
applicable Mission and EP allowances. New Action/run/model IDs do not refresh
repair capacity. Distinguish legitimate new criterion work from disguised retry;
if continuity cannot be represented by the owning contract, block rather than
invent inherited-budget fields or reset the counter. Preserve EP's existing
three-round run/continuation ceiling and any stricter actual authority.
Read-only/docs/design-only effects survive splitting, joining and feedback;
design completion never authorizes implementation. Unknown measurements stay
unknown; no duplicate usage attribution or fabricated historical telemetry.

## Delivery and qualification

| Node | Local predecessors | Bounded delivery |
| --- | --- | --- |
| AS-F-CONTRACT | none | Versioned sizing/fit/evidence and criterion-contribution contract |
| AS-F-POLICY | AS-F-CONTRACT | Qualified presets, thresholds, snapshots and explanations |
| AS-F-PLAN | AS-F-POLICY | Real planner sizing/split/coalesce gate before materialization |
| AS-F-BIND | AS-F-PLAN | Actual submission/profile and rejection/recovery binding |
| AS-F-FEEDBACK | AS-F-BIND | Cause-aware measurements and bounded next-Action adaptation |
| AS-F-Q | AS-F-FEEDBACK | Installed inner-loop and comparative-quality qualification |

AS-F-PLAN additionally consumes AS-E-FIT; AS-F-Q consumes AS-E-Q. Required POL-F,
RMP/SA context/observability, peer-auth and runtime seams are qualified SUBSETS,
not dependencies on complete Console/Workspace/installer programmes. No parent
node depends backwards on this whole family. Workspace delivery is not required
for a headless qualified sizing pilot. All nodes are PLANNED with no receipts.

The [scenario registry](../roadmap/adaptive-action-sizing-v1.json) supplies AS-T01
through AS-T20. Reuse FCI-CONTRACT/HARNESS/EP/FLOW/RESTART/NEGATIVE/CI and retain
FIE-01..28. For sizing support, all applicable new cases are mandatory: installed
real planner/validator/policy/HTTP/reconciliation, only external LLM/OS and EP
boundaries faked. Do not inject a successful sizing decision from a test driver.
Fixture/profile variants need actual producer-contract provenance; do not append
unapproved fields to peer v1.2. Missing public seams are implementation gaps.

CI proves policy behavior, not that a named model or larger batch is better.
Before real policy activation use a separately authorized representative corpus,
predeclared quality/review floors, matched task/effect profiles, success and failure
samples, and measured total cycle effort/latency/repairs. Compare smaller/balanced/
larger presets and record uncertainty; include overhead to penalize micro-steps.
Do not claim savings from toy tasks, incomplete reviews or simulated token counts.

This document changes no running Mission, budget, schema, workflow, model choice
or installed service. First-canary authority stays unchanged. Runtime code/tests,
real producer capability and comparative qualification remain separate delivery.
