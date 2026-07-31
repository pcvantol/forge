# Forge Bootstrap Increment 008 Handoff

## Implemented capability

Engineering Intent Architecture 0.8 establishes Engineering Intent as Forge's
canonical, model-independent engineering artefact. Runtime Prompts are
temporary, provider-specific artefacts derived from an intent and are never
the canonical source of truth.

## Architecture decisions

- An intent carries context, goal, architecture decisions, scope, constraints,
  deliverables, validation, and expected evidence.
- Vision informs intents; Roadmap and Backlog prioritize them; Proposals bound
  and justify them; and Approval authorizes progression without changing them.
- Repository Reality is compared with Engineering Intent to determine
  Repository Drift. Prompts are not the basis for drift.
- Evidence validates outcomes, and Runtime Providers consume only derived
  Runtime Prompts.
- Existing bootstrap prompts are predecessors of Engineering Intents; their
  reconstruction and migration remain future work.

## Limitations

- No runtime, prompt generator, parser, storage model, migration, or execution
  pipeline is introduced.
- Existing 0.7 prompt-artifact contracts and bootstrap behavior are unchanged.

## Validation

Documentation links and existing automated tests must remain valid.
