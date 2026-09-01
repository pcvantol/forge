# AI Development Contract Semantic Equivalence Receipt

- Receipt schema: `1`
- Repository: `pcvantol/forge`
- Reviewed base: `ede4536ec218a5a03951f609cd23adda78d3c8f0`
- Adoption branch: `codex/ai-development-projection`
- Central authority: `pcvantol/ai-development-contracts`
- Central source commit: `ec070e399ff4dbd92e760370002995fe4f4d52d6`
- Profile / extension: `forge` / `FORGE_DEVELOPMENT_EXTENSION`
- Projection digest: `34d04daa1668d5ee1288a22d77aa143fecf4e167cb7fdc443d4082cb3ed45d77`

## Authority result

The committed generated projection is the sole maintained authoring location
for the eight generic AI-development contracts. `FORGE_DEVELOPMENT_EXTENSION`
contains only Forge-specific orientation, product authority and integration
boundaries. Product architecture, repository configuration and immutable
Genesis material remain in their existing Forge-owned locations.

## Section-level matrix

| Source / stable section | Semantic concept | Classification | Contract / surviving location | Cleanup action | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `BOOTSTRAP.md` / generic startup | repository-first bootstrap and validation ordering | GENERIC_PROJECTED | `AI_BOOTSTRAP_CONTRACT`; generated projection | replaced with thin Forge navigation | projection validator + test | PROVEN |
| `BOOTSTRAP.md` / Forge boundaries | product architecture, Workspace peer and installed-EP boundary | FORGE_DEVELOPMENT_EXTENSION | extension + Forge architecture | retained as local navigation | extension links | PROVEN |
| `ENGINEERING_METHOD.md` / generic workflow | bounded work, evidence and handoff mechanics | GENERIC_PROJECTED | bootstrap, prompt, branch and validation contracts | removed duplicate method | projection | PROVEN |
| `ENGINEERING_METHOD.md` / Mission ownership | Mission, approvals, Producer and Execution Host responsibilities | FORGE_PRODUCT_AUTHORITY | engineering-mission, producer and execution-host architecture | retained as local summary | architecture records | PROVEN |
| `PROMPT_INITIALIZATION.md` / generic initialization | scope, authorization and fail-closed prompt mechanics | GENERIC_PROJECTED | `PROMPT_INITIALIZATION_CONTRACT` | replaced with projection link | projection | PROVEN |
| `PROMPT_INITIALIZATION.md` / Forge context | Forge architecture, roadmap and Mission context | FORGE_DEVELOPMENT_EXTENSION | extension and architecture records | retained | offline bootstrap test | PROVEN |
| `AGENTS.md` / generic agent workflow | bootstrap reading and bounded repository work | GENERIC_PROJECTED | generated projection | duplicate instructions retired | projection | PROVEN |
| `AGENTS.md` / Forge role boundary | Mission, host, Business and Architecture ownership | FORGE_PRODUCT_AUTHORITY | Forge architecture | retained | architecture records | PROVEN |
| `README.md` / product current state | Forge generation, architecture, roadmap and runtime scope | FORGE_PRODUCT_AUTHORITY | README and architecture | unchanged | repository truth | PROVEN |
| `docs/governance/managed-repository-baseline.md` / generic governance | reviewability, validation and generic repository governance | GENERIC_PROJECTED | `REPOSITORY_GOVERNANCE_CONTRACT`, `VALIDATION_EVIDENCE_CONTRACT` | marked projection-authoritative | projection | PROVEN |
| `docs/governance/managed-repository-baseline.md` / local state | Forge GitHub rules, CodeQL, security and local TDE profile | FORGE_DEVELOPMENT_EXTENSION | extension + repository-local settings | retained | workflow/configuration | PROVEN |
| `scripts/validate.sh`, CI and tests | Forge commands, test suite and enforcement | FORGE_PRODUCT_AUTHORITY | Forge scripts/workflows/tests | retained; projection validator added | local and hosted CI | PROVEN |
| `.tde.yml` / Forge profile | local `code_size` mapping and evidence invocation | FORGE_TDE_INTEGRATION | extension + `.tde.yml` | retained | TDE commands | PROVEN |
| `docs/handoff/*` / generic handoff form | bounded outcome, evidence and next decision | GENERIC_PROJECTED | `HANDOFF_CONTRACT` | projection is normative | projection | PROVEN |
| `docs/handoff/*` / Forge content | increment, architecture and repository handoff facts | FORGE_DEVELOPMENT_EXTENSION | handoff records + extension | retained | offline bootstrap test | PROVEN |
| `FORGE_GENESIS_PROVENANCE.md` | Genesis root, source head and preservation method | GENESIS_PROVENANCE | provenance document and Git history | retained; current authority link updated | Git ancestry | PROVEN |
| `docs/reports/**`, historical handoffs and commits | past engineering evidence | IMMUTABLE_FORGE_HISTORY | existing history/evidence | unchanged | Genesis lineage | PROVEN |
| Forge architecture, roadmap, planning and runtime docs | Forge product/domain semantics | FORGE_PRODUCT_AUTHORITY | `docs/architecture`, roadmap, models and tests | unchanged | repository truth | PROVEN |
| Forge ↔ Workspace descriptions | peer integration only | FORGE_WORKSPACE_INTEGRATION | extension and architecture | retained | boundary check | PROVEN |
| Forge → installed EP descriptions | future planning-to-execution boundary | FORGE_EP_INTEGRATION | extension and execution-host architecture | retained; no implementation | dependency scan | PROVEN |

## Zero-loss and duplicate audit

- Candidate active development/governance surfaces: 10, plus historical
  reports, handoffs and repository enforcement surfaces.
- Classified semantic sections: 20.
- `UNRESOLVED`: `0`.
- `CENTRAL_CONTRACT_GAP`: `0`.
- Independently maintained generic AI-development authoring copies before
  cleanup: four root entrypoint sections and one managed-baseline section.
- Generic authoring copies after cleanup: `0`.
- Generic semantics survive only as the generated projection or thin links.
- Forge product authority, Workspace peer material, future installed-EP
  boundary, TDE profile, Genesis provenance and immutable history were not
  deleted or reassigned.

## Validation record

- Central pin, exact eight identities, profile, extension identity and digest:
  offline projection validator PASS.
- Projection drift canary: an untouched projection passes; a manual generated
  projection edit fails; a local extension edit is allowed.
- Offline Forge bootstrap canary: passes from Forge-local entrypoints only;
  it discovers identity, provenance, projection, extension, architecture,
  roadmap, validation, TDE, handoff, Workspace peer and installed-EP boundary.
- Full Forge suite: `293` tests passed, `0` failures and `0` skips.
- Static validation: `bash scripts/validate.sh` and `git diff --check` PASS.
- TDE: `validate`, `assess`, and `qualify` for `code_size` PASS; qualification
  level `QUALIFIED`, policy decision `PASS`, no triggered rules.
- Hosted CI and CodeQL are required on the existing pull request; they are
  evaluated after this receipt is pushed. Secret scanning, push protection,
  Dependabot, pinned workflow actions and the main integrity ruleset remain
  repository-local security controls.
