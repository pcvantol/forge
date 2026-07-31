# Prototype / Solo / Local Governance

## Status

Active for Forge Foundation Model 0.2.

## Operating constraints

| Dimension | Forge 0.1 decision |
| --- | --- |
| Engineering mode | `prototype` (available catalog also includes `managed`, `production`, `enterprise`) |
| Governance profile | `solo` (available catalog also includes `two_person`, `team`, `enterprise`) |
| Runtime | Local only |
| Execution provider | Codex CLI through Engineering Platform 1.5 |
| Repository operations | Not implemented |
| Cloud and SaaS | Out of scope |
| Multi-user collaboration | Out of scope |

## Authority

The human owner is the sole governance authority. AI assistance may inspect
local inputs, propose a bounded change, and prepare local artifacts only when
the human has authorized the work. AI assistance must not infer authority to
operate on cataloged repositories or to expand product scope.

## Knowledge and artifact rules

- Knowledge sources are read-only inputs.
- Certified knowledge remains authoritative; generated documents and plans are
  derived artifacts.
- Git is authoritative for the Forge repository and every cataloged repository
  remains authoritative for itself.
- Source identity and provenance must be explicit where Forge later consumes
  outside knowledge.
- Forge artifacts must not include credentials, tokens, private repository
  data, raw prompts, or unreviewed knowledge as authoritative claims.

## Change discipline

Each increment has one bounded purpose, documented validation, and an explicit
human decision before a behavior-changing capability is accepted. Prototype
speed does not waive these boundaries. A future change to governance, runtime,
or execution authority requires its own documented increment.
