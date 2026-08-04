"""Tests for the provider-neutral Execution Host Contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest

from forge.models import (
    ExecutionDispatch,
    ExecutionEvidenceOutcome,
    ExecutionHostContract,
    ExecutionHostEvidence,
    ExecutionHostForbiddenResponsibility,
    ExecutionHostLifecycleStage,
    ExecutionHostResponsibility,
    ExecutionRepositoryEvidence,
    ExecutionRequest,
    ProducerContract,
    ProducerIdentity,
    ProducerType,
    ProviderPromptDefinition,
    RuntimePrompt,
    RuntimePromptSection,
    RuntimePromptSectionKind,
)


def prompt() -> RuntimePrompt:
    return RuntimePrompt(
        "prompt-1", "intent-1", "1", "action-1", ProviderPromptDefinition("provider", "1"),
        "sha256:" + "b" * 64,
        tuple(RuntimePromptSection(kind, (kind.value,)) for kind in RuntimePromptSectionKind),
    )


def request(**overrides: object) -> ExecutionRequest:
    values: dict[str, object] = {
        "host_id": "host-1", "mission_id": "mission-1", "intent_id": "intent-1",
        "intent_revision": "1", "action_id": "action-1", "runtime_prompt": prompt(),
        "workspace_id": "workspace-1", "repository_id": "forge", "correlation_id": "correlation-1",
        "dispatched_at": "2026-08-01T20:00:00Z",
    }
    values.update(overrides)
    return ExecutionRequest(**values)  # type: ignore[arg-type]


def repository_evidence(**overrides: object) -> ExecutionRepositoryEvidence:
    values: dict[str, object] = {
        "mission_id": "mission-1", "intent_id": "intent-1", "intent_revision": "1",
        "action_id": "action-1", "runtime_prompt_id": "prompt-1", "correlation_id": "correlation-1",
        "host_run_id": "run-1", "repository_id": "forge", "repository_revision": "abc123",
        "report_id": "report-1", "content_digest": "sha256:" + "a" * 64,
    }
    values.update(overrides)
    return ExecutionRepositoryEvidence(**values)  # type: ignore[arg-type]


class ExecutionHostContractTests(unittest.TestCase):
    def test_contract_declares_all_required_and_forbidden_responsibilities(self) -> None:
        contract = ExecutionHostContract("host-1", "1", tuple(ExecutionHostResponsibility), tuple(ExecutionHostForbiddenResponsibility), tuple(ExecutionHostLifecycleStage))
        self.assertEqual(set(contract.responsibilities), set(ExecutionHostResponsibility))
        with self.assertRaises(FrozenInstanceError):
            contract.host_id = "other"  # type: ignore[misc]
        self.assertTrue({
            ExecutionHostForbiddenResponsibility.AGENT_ROLE_SELECTION,
            ExecutionHostForbiddenResponsibility.MODEL_PROFILE_SELECTION,
            ExecutionHostForbiddenResponsibility.REASONING_PROFILE_SELECTION,
            ExecutionHostForbiddenResponsibility.EXECUTION_HOST_SELECTION,
        }.issubset(set(contract.forbidden_responsibilities)))

    def test_request_binds_mission_intent_action_prompt_and_retry_identity(self) -> None:
        issued = request()
        self.assertEqual(issued.runtime_prompt.source_action_id, "action-1")
        self.assertIsInstance(issued.producer_contract, ProducerContract)
        self.assertEqual(issued.producer_contract.producer.identity.type, "FORGE")
        self.assertEqual(issued.producer_contract.correlation_id, "correlation-1")
        human_prompt = RuntimePrompt(
            "prompt-2", "intent-1", "1", "action-1", ProviderPromptDefinition("provider", "1"),
            "sha256:" + "c" * 64,
            tuple(RuntimePromptSection(kind, (kind.value,)) for kind in RuntimePromptSectionKind),
            producer_identity=ProducerIdentity("architect-1", ProducerType.HUMAN, "1"),
        )
        self.assertEqual(request(runtime_prompt=human_prompt).producer_contract.producer.identity.type, "HUMAN")
        with self.assertRaisesRegex(ValueError, "Runtime Prompt"):
            request(action_id="other")
        with self.assertRaisesRegex(ValueError, "own correlation"):
            request(retry_of_correlation_id="correlation-1")

    def test_evidence_requires_exact_run_bound_repository_provenance(self) -> None:
        evidence = ExecutionHostEvidence("host-1", "correlation-1", "run-1", "report-1", ExecutionEvidenceOutcome.COMPLETE, repository_evidence(), execution_started_at="2026-08-04T10:00:00Z", execution_completed_at="2026-08-04T10:01:00Z", receipt_id="receipt-1", execution_duration_ms=60_000)
        self.assertEqual(evidence.repository_evidence.runtime_prompt_id, "prompt-1")
        with self.assertRaisesRegex(ValueError, "run and report"):
            replace(evidence, host_run_id="other")

    def test_dispatch_requires_a_host_run_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "host run"):
            ExecutionDispatch(request(), "")

    def test_contract_model_does_not_depend_on_a_renderer(self) -> None:
        import forge.models.execution_host as boundary
        self.assertNotIn("codex_runtime_prompt", boundary.__dict__)


if __name__ == "__main__":
    unittest.main()
