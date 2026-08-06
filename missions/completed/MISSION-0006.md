# MISSION-0006 — Portfolio Intelligence Foundation

## Mission identity

- Mission type: Business Mission
- Generation: 2
- Lifecycle: complete
- Business approval: approved
- Architecture approval: approved for engineering
- Runtime Instance: `forge-runtime-7bba2467-eca6-49fc-98d8-b67da0d43b33`
- Completion timestamp: `2026-08-06T06:08:17Z`
- Completion Decision Evidence: `MISSION-0006-mission-completion-decision-1`

## Business objective

Enable Forge to analyse Repository Truth, Runtime Instance and historical
Decision Evidence in order to recommend evidence-based future Mission
Candidates, including governed repository-maintenance opportunities. This
reduces manual roadmap planning, improves portfolio prioritisation, supports
deterministic Business decisions and preserves canonical governance.

## Scope

Create the Portfolio Intelligence Foundation contracts and evidence paths that
can form recommendations. Preserve separate Business and Architecture approval
and keep Mission ownership in Forge.

## Out of scope

- Implementing Portfolio Intelligence recommendations or autonomous portfolio decisions.
- Executing an Engineering Action before its separate runtime admission.
- Bypassing Business approval, Architecture approval or Execution Policy.
- Moving Engineering Platform ownership into Forge.

## Governance lifecycle

```text
Business review → Business approved → Architecture review
→ Approved for engineering → Mission Dispatcher → Runtime Instance
```

The approvals are distinct auditable events, even when one operator holds both
roles. The authoritative Runtime Instance records this Mission as complete;
the Dispatcher is `IDLE` and the approved Mission Queue is empty.

## Initial Decision Evidence

`MISSION-0006-intake-evidence-1` records why this Mission is recommended,
its Business and architectural value, expected repository impact, alternatives
considered and high confidence. It is dedicated pre-approval intake evidence;
it does not claim non-existent Execution Evidence.

## Completed engineering plan

| Engineering Intent | Engineering Actions | Runtime prompts |
| --- | ---: | ---: |
| Repository Truth and Runtime Evidence Foundation | 2 | 2 |
| Governed Mission Candidate Recommendation Boundary | 1 | 1 |

Total: 2 Engineering Intents and 3 Engineering Actions. The authoritative
Runtime Instance records both Intents and all three Actions as `COMPLETED`.
The dependency-ordered action receipts are bound to these local Genesis
commits:

- `MISSION-0006-action-repository-truth`: `925b7d9`
- `MISSION-0006-action-runtime-evidence`: `7426791`
- `MISSION-0006-action-mission-candidates`: `8659784`

The Mission completion evidence binds the final receipt to
`MISSION-0006-mission-completion-decision-1` and records an outcome of
`complete`.

## Completion evidence

`MISSION-0006-planning-decision-1` records the original sequential action
selection. `MISSION-0006-runtime-evidence-execution-decision-1` and
`MISSION-0006-mission-candidate-origin-decision-1` preserve the bounded
implementation decisions. `MISSION-0006-mission-completion-decision-1`
records that all dependency-ordered actions have complete local Genesis
receipts and that the Mission may close.

## Success criteria

- Repository Truth, Runtime Instance and Decision Evidence have explicit,
  bounded inputs for portfolio analysis.
- Recommendations retain Mission Origin, Repository Evidence, Business Value,
  Expected Engineering Value, Risk if Deferred, Dependencies, Confidence,
  Recommendation Source and Decision Evidence in the Runtime Instance.
- Recommendations remain advisory until a new Mission Candidate separately
  passes the identical Business then Architecture governance lifecycle,
  including maintenance-origin work.
- All provenance is deterministic, local and auditable.
