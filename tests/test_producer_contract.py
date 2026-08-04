"""Regression coverage for the canonical Forge-owned Producer Contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from forge.models import (
    DEFAULT_FORGE_PRODUCER,
    ExecutionReceiptReference,
    Producer,
    ProducerContract,
    ProducerIdentity,
    ProducerType,
    RuntimePromptEnvelope,
)


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

    def test_contract_version_and_required_identity_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "version"):
            contract(contract_version="2.0")
        with self.assertRaisesRegex(ValueError, "constraints"):
            contract(execution_constraints=())


if __name__ == "__main__":
    unittest.main()
