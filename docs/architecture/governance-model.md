# Forge Governance Model

Engineering Mode and Governance Profile are independent value catalogs.

| Contract | Available values | Bootstrap-active value |
| --- | --- | --- |
| Engineering Mode | `prototype`, `managed`, `production`, `enterprise` | `prototype` |
| Governance Profile | `solo`, `two_person`, `team`, `enterprise` | `solo` |

The full catalogs preserve forward compatibility; selecting `prototype` and
`solo` during bootstrap does not erase the other valid concepts. The active
selection is stored on Workspace. It grants no runtime authority. Human
approval remains mandatory for future behaviour-changing capabilities.

## Portfolio-driven approval boundary

Forge uses two explicit human approvals before engineering may begin:

```text
Business Owner → approve Mission Candidate for Architecture
Platform Architect → approve Mission for Engineering
Forge → engineer only within the approved Mission
```

The Business Workspace owns candidates, portfolio priority, business value,
and strategic alignment. The Architecture Workspace owns technical feasibility,
scope, architectural boundaries, and engineering constraints. Forge never
bypasses either approval and never changes a Mission objective. The canonical
lifecycle and advisory feedback loop are in the [Product Model](product-model.md).

Schemas: `engineering-mode.schema.json` and `governance-profile.schema.json`.
