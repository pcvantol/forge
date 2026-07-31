# Forge Engineering Prompt Artifact Foundation 0.7

An Engineering Prompt Artifact is a versioned, repository-independent
engineering instruction derived from an approved Engineering Proposal. It
preserves identity, source-proposal version, workspace and repository context,
engineering mode, governance profile, capability references, objective, scope,
typed evidence references, execution instructions, and validation
requirements.

`EngineeringPromptArtifactGenerator` is local and deterministic: all variable
content, including the creation timestamp, is supplied explicitly. It verifies
that the source proposal is `APPROVED` and belongs to the supplied workspace.
It does not read evidence, call a provider, operate a repository, or make an
approval decision.

The artifact lifecycle is deliberately small: `DRAFT` then `READY`. The
explicit transition to `READY` makes an instruction available to a future
runtime provider, but does not invoke it or authorize execution. Execution
instructions remain provider-neutral declarations; they contain no Codex CLI
commands or provider-specific behavior.
