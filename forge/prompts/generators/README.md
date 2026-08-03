# Prompt Generators

This is the canonical location for Forge-owned Runtime Prompt Generators.
Generators transform an approved Engineering Intent and declared versioned
context into a transient Runtime Prompt. Increment 1.9 provides the abstract
deterministic generator contract. Increment 3.3 adds the separate concrete
Codex CLI presentation renderer in `forge/prompts/codex_cli.py`; its canonical
contract is documented in
[`docs/architecture/codex-cli-runtime-prompt-renderer.md`](../../../docs/architecture/codex-cli-runtime-prompt-renderer.md).

The renderer remains non-executing and does not change Engineering Intent
semantics or communicate with an Execution Host.
