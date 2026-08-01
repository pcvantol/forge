# AI Provider Registry

This is the canonical repository location for the provider-neutral registry.
The executable registry contract is deliberately local and non-executing in
`forge.ai_architect.provider_registry`. It stores declarations and performs
deterministic selection only; it never loads, configures, or invokes a model.
