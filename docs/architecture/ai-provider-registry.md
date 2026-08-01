# AI Provider Registry 1.7

## Purpose

The AI Provider Registry is Forge's canonical, provider-neutral model for
discovering registered AI Architect Providers and selecting one declaration
deterministically. It provides no provider implementation, model loading,
prompt generation, or AI execution.

Forge depends only on the [AI Architect Provider Contract](ai-architect-provider.md).
It never depends upon OpenAI, Claude, Gemini, local models, or any other model
vendor.

## Registration and metadata

Every provider registers immutable `AIProviderMetadata` with an identity,
version, provider type, explicitly declared capabilities, supported reasoning
modes, qualification state, and status. The initial closed capability
catalogue is Architecture Reasoning, Engineering Proposal Generation,
Engineering Intent Drafting, Knowledge Distillation, and Architecture Review.

The canonical code location is `forge/models/ai_provider_registry.py`; the
canonical documentation location for future metadata is
`forge/ai_architect/providers/metadata/`. Registration records declarations
only. It neither imports an adapter nor validates a vendor integration.

## Qualification

Qualification is repository-owned rather than provider-owned. A
`ProviderQualification` binds the registered provider identity and version to a
repository reference and one state: `REGISTERED`, `QUALIFIED`,
`EXPERIMENTAL`, `DEPRECATED`, or `RETIRED`. A registration is valid only when
its metadata and qualification record state agree.

Only an `ACTIVE`, `QUALIFIED` provider is eligible for selection. Experimental,
deprecated, retired, registered-only, and inactive declarations remain visible
registry evidence but cannot be selected. The canonical documentation location
is `forge/ai_architect/providers/qualification/`.

## Deterministic selection

Selection is declarative and has no invocation step:

```text
Workspace
  ↓
Requested Capability + Reasoning Mode
  ↓
Active Qualified Providers
  ↓
Workspace Preference → Default Provider → Fallback Provider → Provider ID/Version
  ↓
Selection
  ↓
Future Invocation Boundary
```

The registry first filters by active status, qualification, declared capability,
and declared reasoning mode. It then considers an ordered workspace preference,
the workspace default provider, and the fallback provider. If none applies, it
uses ascending provider identity and version as its stable tie-breaker. If no
eligible declaration exists, selection fails without substituting a provider or
executing a request.

## Workspace configuration

`WorkspaceProviderConfiguration` captures a workspace identity, optional
default provider, ordered provider preferences, and optional fallback provider.
It is a policy declaration only. It contains no credentials, vendor settings,
runtime model configuration, prompts, or execution controls.

The canonical registry location is `forge/ai_architect/registry/` with the
local selection contract in `forge/ai_architect/provider_registry.py`.

## Future providers

Future concrete providers belong in `forge/ai_architect/providers/` and must
implement the existing request/result contract in a separately authorized
increment. They must first be registered and repository-qualified. Provider
implementation, runtime invocation, prompt generation, Studio, and AI
execution remain out of scope for this increment.
