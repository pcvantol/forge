# Forge Engineering Prompt Artifact Foundation 0.7

An Engineering Prompt Artifact is a versioned, repository-independent
provider-neutral instruction form derived from an approved Engineering Proposal. It
preserves identity, source-proposal version, workspace and repository context,
engineering mode, governance profile, capability references, objective, scope,
typed evidence references, execution instructions, and validation
requirements.

The model can render itself as deterministic Markdown for human review and
future runtime consumption. The rendering includes every artifact field in a
fixed order; it remains an instruction artifact, not an executable command.

Since Engineering Intent Architecture 0.8, this 0.7 form is explicitly not the
canonical engineering instruction. The canonical, model-independent source of
truth is Engineering Intent. The 0.7 artifact is the retained transitional
execution representation from bootstrap: it remains compatible until Runtime
Providers are implemented, but it neither replaces an intent nor determines
Repository Drift. A future Runtime Prompt is derived from Engineering Intent,
not from a Prompt Artifact.

`EngineeringPromptArtifactGenerator` is local and deterministic: all variable
content, including the creation timestamp, is supplied explicitly. It verifies
that the source proposal is `APPROVED` and belongs to the supplied workspace.
It does not read evidence, call a provider, operate a repository, or make an
approval decision.

The artifact lifecycle is deliberately small: `DRAFT` then `READY`. The
explicit transition to `READY` makes the transitional representation available
for compatible bootstrap transport, but does not invoke a provider or
authorize execution. Execution instructions remain provider-neutral
declarations; they contain no Codex CLI commands or provider-specific
behavior. Forge 0.8 changes no 0.7 schema, generator, lifecycle, or bootstrap
behavior.

Forge retains versioned instructions for bootstrap compatibility. Once Runtime
Providers exist, they consume provider-specific Runtime Prompts derived from
Engineering Intent under separately governed human approval. That provider
boundary must not reinterpret the intent, bypass approval, or change a
repository merely by reading a transitional Prompt Artifact.
