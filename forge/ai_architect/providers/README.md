# AI Architect Providers

This is the canonical future location for qualified AI Architect Provider
implementations. It intentionally contains no provider implementation.

Adapters must consume `forge.models.AIArchitectRequest` and return only an
advisory `forge.models.AIArchitectResult`. They may not duplicate Forge
knowledge, mutate source material, create governed Proposals or Intents, make
approval decisions, invoke Runtime Providers, or execute engineering.

Registration, qualification, and deterministic selection are documented in
[`docs/architecture/ai-provider-registry.md`](../../../docs/architecture/ai-provider-registry.md).
The Provider Contract continues to define the adapter boundary in
[`docs/architecture/ai-architect-provider.md`](../../../docs/architecture/ai-architect-provider.md).
