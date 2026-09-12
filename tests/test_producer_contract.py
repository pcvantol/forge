"""Regression coverage for the canonical Forge-owned Producer Contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from forge.models import (
    DEFAULT_FORGE_PRODUCER,
    ExecutionReceiptReference,
    ForgeActionContextEnvelope,
    ForgePlanningContextEnvelope,
    Producer,
    ProducerContract,
    ProducerIdentity,
    ProducerType,
    RuntimePromptEnvelope,
)
from forge._version import canonical_version


def contract(**overrides: object) -> ProducerContract:
    values: dict[str, object] = {
        "producer": DEFAULT_FORGE_PRODUCER,
        "correlation_id": "correlation-1",
        "mission_id": "mission-1",
        "engineering_action_id": "action-1",
        "runtime_prompt": RuntimePromptEnvelope("prompt-1", "1.0", "text/markdown", "# Prompt", "sha256:" + "a" * 64),
        "execution_constraints": ("no host-specific planning",),
        "execution_metadata": (("repository_id", "forge"),),
    }
    values.update(overrides)
    return ProducerContract(**values)  # type: ignore[arg-type]


class ProducerContractTests(unittest.TestCase):
    def test_planning_context_is_versioned_redacted_and_keeps_only_an_opaque_decision_reference(self) -> None:
        context = ForgePlanningContextEnvelope.create(
            mission_id="mission-1", mission_revision="7", intent_id="intent-1", intent_revision="3",
            action_id="action-1", mission_title="Mission api_key=should-not-leave-forge",
            business_summary="Deliver the bounded business result.",
            engineering_summary="Implement token=should-not-leave-forge safely.",
            mission_lifecycle="ACTIVE", decision_evidence_reference="architecture-review:mission-1",
        )
        document = context.to_dict()
        self.assertEqual(document["mission_title"], "Mission api_key=[REDACTED]")
        self.assertEqual(document["engineering_summary"], "Implement token=[REDACTED] safely.")
        self.assertEqual(document["mission_lifecycle"], "ACTIVE")
        self.assertEqual(document["decision_evidence_reference"], "architecture-review:mission-1")
        self.assertTrue(str(document["decision_evidence_reference_digest"]).startswith("sha256:"))
        self.assertTrue(str(document["envelope_digest"]).startswith("sha256:"))
        with self.assertRaisesRegex(ValueError, "opaque"):
            ForgePlanningContextEnvelope.create(
                mission_id="mission-1", mission_revision="7", intent_id="intent-1", intent_revision="3",
                action_id="action-1", decision_evidence_reference="not an opaque evidence reference",
            )

    def test_action_context_is_immutable_redacted_and_digest_bound(self) -> None:
        context = ForgeActionContextEnvelope.create(
            action_id="action-1",
            summary="Rotate api_key=super-secret and use Bearer abcdefghijklmnop.",
            source_digest="sha256:" + "b" * 64,
        )
        document = context.to_dict()
        self.assertEqual(document["summary"], "Rotate api_key=[REDACTED] and use Bearer [REDACTED].")
        self.assertEqual(document["generator"], {
            "id": "forge-redacted-action-summary",
            "model": "deterministic-template",
            "version": "1.0",
            "source_digest": "sha256:" + "b" * 64,
        })
        self.assertTrue(str(document["summary_digest"]).startswith("sha256:"))
        self.assertTrue(str(document["envelope_digest"]).startswith("sha256:"))
        with self.assertRaises(FrozenInstanceError):
            context.summary = "changed"  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "digest"):
            ForgeActionContextEnvelope(
                action_id=context.action_id, summary=context.summary, source_digest=context.source_digest,
                summary_digest=context.summary_digest, envelope_digest="sha256:" + "0" * 64,
            )

    def test_default_execution_contract_derives_context_only_from_objective(self) -> None:
        from forge.models.execution_host import ExecutionRequest
        from forge.models.runtime_prompt import ProviderPromptDefinition, RuntimePrompt, RuntimePromptSection, RuntimePromptSectionKind

        sections = tuple(
            RuntimePromptSection(
                kind,
                ("Safe action objective api_key=not-for-EP",) if kind is RuntimePromptSectionKind.OBJECTIVE else (kind.value,),
            )
            for kind in RuntimePromptSectionKind
        )
        prompt = RuntimePrompt(
            "prompt-1", "intent-1", "1", "action-1", ProviderPromptDefinition("provider", "1"),
            "sha256:" + "c" * 64, sections, mission_id="mission-1",
            execution_metadata=(("mission_revision", "1"),),
        )
        request = ExecutionRequest(
            "engineering-platform", "mission-1", "intent-1", "1", "action-1", prompt,
            "workspace-1", "forge", "correlation-1", "2026-09-12T00:00:00Z",
        )
        context = request.producer_contract.action_context
        self.assertIsNotNone(context)
        self.assertEqual(context.summary, "Safe action objective api_key=[REDACTED]")
        self.assertEqual(context.source_digest, prompt.generation_request_digest)

    def test_default_forge_producer_reports_the_canonical_application_release(self) -> None:
        self.assertEqual(DEFAULT_FORGE_PRODUCER.identity.version, canonical_version())
        self.assertEqual(DEFAULT_FORGE_PRODUCER.contract_version, "1.0")

    def test_model_is_immutable_and_type_is_extensible(self) -> None:
        human = Producer(ProducerIdentity("architect-1", ProducerType.HUMAN, "1.0"))
        external = Producer(ProducerIdentity("partner-1", "PARTNER_SYSTEM", "2"))
        self.assertEqual(human.identity.type, "HUMAN")
        self.assertEqual(external.identity.type, "PARTNER_SYSTEM")
        with self.assertRaises(FrozenInstanceError):
            human.identity.id = "other"  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "uppercase"):
            ProducerIdentity("x", "not extensible", "1")

    def test_serialisation_and_identity_are_deterministic(self) -> None:
        first = contract(execution_metadata=(("z", "last"), ("a", "first")))
        second = contract(execution_metadata=(("a", "first"), ("z", "last")))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(first.to_dict()["producer"]["identity"], DEFAULT_FORGE_PRODUCER.identity.to_dict())

    def test_contract_carries_only_host_references_not_host_implementation(self) -> None:
        item = contract(
            receipt_references=(ExecutionReceiptReference("host-1", "receipt-1"),),
            execution_evidence_references=("host://evidence/1",),
        )
        document = item.to_dict()
        self.assertEqual(document["receipt_references"][0]["host_id"], "host-1")
        self.assertEqual(document["engineering_action_id"], "action-1")
        self.assertNotIn("engineering_platform", repr(item).lower())

    def test_contract_rejects_context_for_another_action(self) -> None:
        context = ForgeActionContextEnvelope.create(
            action_id="other-action", summary="Safe summary", source_digest="sha256:" + "d" * 64,
        )
        with self.assertRaisesRegex(ValueError, "Action context"):
            contract(action_context=context)

    def test_contract_rejects_planning_context_that_conflicts_with_immutable_metadata(self) -> None:
        context = ForgePlanningContextEnvelope.create(
            mission_id="mission-1", mission_revision="7", intent_id="intent-1", intent_revision="3",
            action_id="action-1",
        )
        with self.assertRaisesRegex(ValueError, "planning context"):
            contract(
                planning_context=context,
                execution_metadata=(("mission_revision", "6"), ("intent_id", "intent-1"), ("intent_revision", "3")),
            )

    def test_contract_version_and_required_identity_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "version"):
            contract(contract_version="2.0")
        with self.assertRaisesRegex(ValueError, "constraints"):
            contract(execution_constraints=())


if __name__ == "__main__":
    unittest.main()
