# Capability Delegation Framework

## Decision

Forge owns the Mission, Mission State, planning, governance and Decision Evidence. A provider owns only execution of a bounded Engineering Action. Mission ownership is never delegated.

## Registry and assessment

The versioned Capability Registry records each capability's stable identity, name, owner, availability, execution mode, preferred provider, trust level and approval requirement. Supported targets are Internal Forge, Human, External Forge Runner, External AI Agent, External Application and Professional Service. The registry is configuration, not an integration.

Before an Action reaches an Execution Host, the loop maps the Action's approved capability impact to a registry record. An available internal capability proceeds normally. An unavailable capability produces a Delegation Request with selected provider, rationale, alternatives, confidence, approval state and decision-evidence references. Missing registry entries fail closed.

## Lifecycle

```text
READY → capability assessment → WAITING_EXTERNAL_CAPABILITY
  → WAITING_EXTERNAL_APPROVAL (when required)
  → WAITING_EXTERNAL_RESULT → result verification
  → READY_TO_CONTINUE → Mission Planner → next Engineering Action
```

Forge persists requests in Mission State and Runtime Database. The framework does not call a provider. A result may be received, accepted, rejected or require additional work. Only explicit successful verification accepts delegated work; acceptance completes precisely that Action and preserves remaining planned Actions. Rejection returns the Mission to the external-capability pause without skipping work.

## Governance and limits

Delegation uses existing Business and Architecture approvals and resolved Execution Policy; it cannot bypass either. Every assessment and delegation records unavailable-capability rationale, provider selection, alternatives, confidence, approval and result-verification provenance as durable Decision Evidence inputs. Mission State history remains append-only.

The Mission Planner is re-invoked before continuation. Business Workspace and Architecture Workspace retain authority. The Execution Host remains independent and does not see provider approval or delegation records.

This increment implements no provider integration, cloud/API execution, GitHub execution, WordPress execution or professional-service connection.
