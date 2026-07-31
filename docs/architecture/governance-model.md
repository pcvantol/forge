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

Schemas: `engineering-mode.schema.json` and `governance-profile.schema.json`.
