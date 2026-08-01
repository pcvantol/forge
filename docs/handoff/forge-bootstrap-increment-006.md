# Forge Bootstrap Increment 006 Handoff

## Implemented capability

Engineering Proposal Generator Foundation 0.6 deterministically transforms a
validated Workspace, Engineering Plan, Engineering Goals, increment proposals,
and evidence references into a local Engineering Proposal artifact. The output
is a governed intention, never an execution instruction.

## Created and changed files

- `forge/proposals/generator.py`
- `forge/models/proposal.py`
- `schemas/engineering-proposal-0.6.schema.json`
- `tests/test_engineering_proposals.py`
- `docs/architecture/engineering-proposals.md`
- `docs/handoff/forge-bootstrap-increment-006.md`

## Architecture decisions

- Proposal creation is deterministic and local; it does not use an LLM or an
  Architect Provider.
- Evidence is mandatory and preserved by reference, without reading or
  changing its source.
- Scope contains bounded included and excluded work plus unique affected
  capabilities.
- Lifecycle labels are declarative. The generator emits `DRAFT`; neither a
  lifecycle transition nor a proposal grants approval or execution authority.

## Validation evidence

Automated tests cover valid deterministic generation, required context,
required evidence, invalid scope, retained evidence references, and lifecycle
transition ordering. `git diff --check` is required before acceptance.

## Limitations

There is no LLM reasoning, Architect Chat, backlog refinement, queue, Inbox,
runtime provider, Codex integration, Studio UI, multi-user approval, repository
operation, or execution capability.

## Recommended next increment

Evaluate the resulting repository state before authorizing the next bounded
capability. A future prompt-artifact layer may consume a human-approved
proposal, but must preserve provenance and human authority.
