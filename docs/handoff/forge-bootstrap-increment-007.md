# Forge Bootstrap Increment 007 Handoff

## Implemented capability

Engineering Prompt Artifact Foundation 0.7 adds a deterministic, versioned,
repository-independent instruction artifact. It transforms an approved 0.6
Engineering Proposal into a `DRAFT` artifact that carries context, objective,
scope, evidence, provider-neutral execution instructions, and validation
requirements. The only lifecycle transition is explicit `DRAFT` to `READY`.

## Architecture decisions

- Creation time is an explicit generator input to preserve deterministic output.
- The generator rejects a source proposal unless it is `APPROVED` and scoped to
  the supplied workspace.
- Context contains repository identity/reference and the workspace's selected
  mode and governance profile; it does not resolve or operate that repository.
- Evidence remains typed references and is never read, copied, or promoted.
- Ready artifacts remain instructions only: no provider invocation, execution,
  mutation, approval, or provider-specific command is included.

## Limitations

- No runtime provider, queue, repository operation, API, approval workflow, or
  artifact persistence is included.
- Artifact input is supplied by the caller; this increment does not derive or
  assess validation content.

## Recommended next increment

Define the governed runtime-provider boundary that may consume a `READY`
artifact, with explicit human approval and execution safeguards.
