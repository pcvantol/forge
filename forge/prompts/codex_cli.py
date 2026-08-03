"""Deterministic, non-executing Codex CLI Runtime Prompt presentation."""

from __future__ import annotations

import hashlib

from forge.models.codex_runtime_prompt import CodexCliRuntimePrompt, CodexCliRuntimePromptRequest


class CodexCliRuntimePromptRenderer:
    """Render one Mission-pinned active Action without planning or execution."""

    def render(self, request: CodexCliRuntimePromptRequest) -> CodexCliRuntimePrompt:
        source_digest = request.digest()
        prompt_id = "codex-cli-runtime-prompt:" + source_digest.removeprefix("sha256:")
        correlation_id = "codex-cli-render:" + hashlib.sha256(
            f"{request.mission.id}\0{request.mission.revision}\0{request.intent.id}\0"
            f"{request.intent.revision}\0{request.action.id}\0{source_digest}".encode("utf-8")
        ).hexdigest()
        return CodexCliRuntimePrompt(
            id=prompt_id,
            correlation_id=correlation_id,
            renderer_version=request.renderer_version,
            schema_version=request.schema_version,
            generated_at=request.repository_state.captured_at,
            mission_id=request.mission.id,
            mission_revision=request.mission.revision,
            intent_id=request.intent.id,
            intent_revision=request.intent.revision,
            action_id=request.action.id,
            repository_state=request.repository_state,
            compatibility=request.compatibility,
            policy_version=request.policy_selection.policy_version if request.policy_selection else None,
            policy_digest=request.policy_selection.digest() if request.policy_selection else None,
            policy_execution_constraints=(request.policy_selection.execution_constraints.prompt_constraints()
                                          if request.policy_selection else ()),
            objective=request.action.objective,
            expected_repository_evidence=request.action.expected_evidence,
            constraints=request.constraints,
            validation=request.validation,
            source_digest=source_digest,
            rendered_text=self._render_text(request, prompt_id, correlation_id),
        )

    @staticmethod
    def _render_text(request: CodexCliRuntimePromptRequest, prompt_id: str, correlation_id: str) -> str:
        compatibility = request.compatibility
        lines = [
            "# Codex CLI Runtime Prompt",
            "",
            f"Runtime Prompt ID: {prompt_id}",
            f"Correlation ID: {correlation_id}",
            f"Renderer version: {request.renderer_version}",
            f"Prompt schema version: {request.schema_version}",
            f"Generation timestamp: {request.repository_state.captured_at}",
            "",
            "## Mission identity",
            "",
            f"- Mission: {request.mission.id} ({request.mission.revision})",
            f"- Mission title: {request.mission.title}",
            f"- Mission objective: {request.mission.objective}",
            "- Mission in-scope boundaries:",
            *[f"  - {item}" for item in request.mission.scope.in_scope],
            "- Mission out-of-scope boundaries:",
            *[f"  - {item}" for item in request.mission.scope.out_of_scope],
            "",
            "## Engineering Intent context",
            "",
            f"- Engineering Intent: {request.intent.id} ({request.intent.revision})",
            f"- Intent title: {request.intent.title}",
            f"- Intent objective: {request.intent.objective}",
            "",
            "## Engineering Action identity",
            "",
            f"- Engineering Action: {request.action.id}",
            "",
            "## Engineering objective",
            "",
            request.action.objective,
            "",
            "## Repository context",
            "",
            f"- Repository: {request.repository_state.repository_id}",
            f"- Revision: {request.repository_state.revision}",
            f"- State digest: {request.repository_state.state_digest}",
            "",
            "## Execution constraints",
            "",
            *[f"- {item}" for item in request.constraints],
            *([] if not request.policy_selection else [
                "- Forge policy execution constraints:",
                *[f"  - {item}" for item in request.policy_selection.execution_constraints.prompt_constraints()],
            ]),
            "",
            "## Expected validation",
            "",
            *[f"- {item}" for item in request.validation],
            "",
            "## Expected repository evidence",
            "",
            *[f"- {item}" for item in request.action.expected_evidence],
            "",
            "## Execution Host compatibility",
            "",
            f"- Execution Host Contract version: {compatibility.execution_host_contract_version}",
            f"- Execution mode: {compatibility.execution_mode}",
            f"- Minimum supported runtime: {compatibility.minimum_supported_runtime}",
            "- Required capabilities:",
            *[f"  - {item}" for item in compatibility.required_capabilities],
            *([] if not request.policy_selection else [
                "",
                "## Forge policy provenance",
                "",
                f"- Policy version: {request.policy_selection.policy_version}",
                f"- Policy digest: {request.policy_selection.digest()}",
            ]),
            "",
            "Repository Truth remains authoritative. Execute only this Engineering Action; do not plan, create, or modify Engineering Actions.",
            "",
        ]
        return "\n".join(lines)
