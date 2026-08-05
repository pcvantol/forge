# MISSION-0006 — Portfolio Intelligence Foundation

## Mission identity

- Mission type: Business Mission
- Generation: 2
- Lifecycle: active; the next Engineering Action is planned and ready for Engineering Platform execution
- Business approval: approved
- Architecture approval: approved for engineering
- Runtime Instance: `forge-runtime-7bba2467-eca6-49fc-98d8-b67da0d43b33`
- Decision Evidence: `MISSION-0006-intake-evidence-1`

## Business objective

Enable Forge to analyse Repository Truth, Runtime Instance and historical
Decision Evidence in order to recommend evidence-based future Mission
Candidates. This reduces manual roadmap planning, improves portfolio
prioritisation, supports deterministic Business decisions and preserves
canonical governance.

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
roles. The dispatcher has registered this Mission; it has not submitted a
Runtime Prompt to Engineering Platform.

## Initial Decision Evidence

`MISSION-0006-intake-evidence-1` records why this Mission is recommended,
its Business and architectural value, expected repository impact, alternatives
considered and high confidence. It is dedicated pre-approval intake evidence;
it does not claim non-existent Execution Evidence.

## Persisted engineering plan

| Engineering Intent | Engineering Actions | Runtime prompts |
| --- | ---: | ---: |
| Repository Truth and Runtime Evidence Foundation | 2 | 2 |
| Governed Mission Candidate Recommendation Boundary | 1 | 1 |

Total: 2 Engineering Intents and 3 Engineering Actions. The active runtime
plan persists the canonical Intent and Action records, selects only
`MISSION-0006-action-repository-truth` for the next Engineering Platform
iteration, and retains the other two actions as dependency-ordered pending
work. The generated runtime prompt is an execution handoff, not completion
evidence.

## Planning evidence

`MISSION-0006-planning-decision-1` records the activation and sequential
action selection. It preserves the distinction between Forge planning and
Engineering Platform execution: no execution receipt is claimed until the
Platform returns one for the selected action.

## Success criteria

- Repository Truth, Runtime Instance and Decision Evidence have explicit,
  bounded inputs for portfolio analysis.
- Recommendations remain advisory until a new Mission Candidate separately
  passes Business and Architecture governance.
- All provenance is deterministic, local and auditable.
