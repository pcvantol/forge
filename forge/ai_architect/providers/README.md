# AI Architect Providers

This is the canonical future location for qualified AI Architect Provider
implementations. It intentionally contains no provider implementation.

Adapters must consume `forge.models.AIArchitectRequest` and return only an
advisory `forge.models.AIArchitectResult`. They may not duplicate Forge
knowledge, mutate source material, create governed Proposals or Intents, make
approval decisions, invoke Runtime Providers, or execute engineering.

Provider registration, qualification, selection, invocation, evidence capture,
and retirement are documented in
[`docs/architecture/ai-architect-provider.md`](../../../docs/architecture/ai-architect-provider.md).
