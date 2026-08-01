"""Tests for the immutable, non-executing Execution Host Contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest

from forge.models import (
    ExecutionEvidenceOutcome,
    ExecutionHostContract,
    ExecutionHostEvidence,
    ExecutionHostForbiddenResponsibility,
    ExecutionHostLifecycleStage,
    ExecutionHostResponsibility,
    ExecutionRepositoryEvidence,
)


def host_contract(**overrides: object) -> ExecutionHostContract:
    values: dict[str, object] = {
        "host_id": "engineering-platform-1.5",
        "version": "1.5",
        "responsibilities": tuple(ExecutionHostResponsibility),
        "forbidden_responsibilities": tuple(ExecutionHostForbiddenResponsibility),
        "lifecycle": tuple(ExecutionHostLifecycleStage),
    }
    values.update(overrides)
    return ExecutionHostContract(**values)  # type: ignore[arg-type]


def repository_evidence(**overrides: object) -> ExecutionRepositoryEvidence:
    values: dict[str, object] = {
        "action_id": "action-1",
        "runtime_prompt_id": "prompt-1",
        "execution_id": "execution-1",
        "repository_id": "forge",
        "repository_revision": "abc123",
        "report_id": "report-1",
        "content_digest": "sha256:" + "a" * 64,
    }
    values.update(overrides)
    return ExecutionRepositoryEvidence(**values)  # type: ignore[arg-type]


class ExecutionHostContractTests(unittest.TestCase):
    def test_contract_declares_all_required_and_forbidden_responsibilities(self) -> None:
        contract = host_contract()
        self.assertEqual(set(contract.responsibilities), set(ExecutionHostResponsibility))
        self.assertEqual(set(contract.forbidden_responsibilities), set(ExecutionHostForbiddenResponsibility))
        self.assertIn(ExecutionHostResponsibility.EXECUTION_EVIDENCE, contract.responsibilities)
        self.assertIn(ExecutionHostForbiddenResponsibility.GOVERNANCE, contract.forbidden_responsibilities)
        with self.assertRaises(FrozenInstanceError):
            contract.host_id = "other"  # type: ignore[misc]

    def test_contract_rejects_incomplete_responsibilities_or_lifecycle(self) -> None:
        with self.assertRaisesRegex(ValueError, "required responsibility"):
            host_contract(responsibilities=tuple(ExecutionHostResponsibility)[:-1])
        with self.assertRaisesRegex(ValueError, "forbidden responsibility"):
            host_contract(forbidden_responsibilities=tuple(ExecutionHostForbiddenResponsibility)[:-1])
        with self.assertRaisesRegex(ValueError, "lifecycle"):
            host_contract(lifecycle=tuple(ExecutionHostLifecycleStage)[:-1])

    def test_repository_evidence_requires_complete_action_prompt_and_repository_provenance(self) -> None:
        evidence = repository_evidence()
        self.assertEqual(evidence.runtime_prompt_id, "prompt-1")
        self.assertEqual(evidence.repository_revision, "abc123")
        with self.assertRaisesRegex(ValueError, "provenance"):
            repository_evidence(runtime_prompt_id="")
        with self.assertRaisesRegex(ValueError, "sha256"):
            repository_evidence(content_digest="abc123")

    def test_host_evidence_envelope_matches_repository_evidence_and_preserves_observability_references(self) -> None:
        repository = repository_evidence()
        evidence = ExecutionHostEvidence(
            "engineering-platform-1.5", "execution-1", "report-1",
            ExecutionEvidenceOutcome.COMPLETE, repository,
            ("log://run-1",), ("diagnostic://run-1",), ("metric://run-1",),
        )
        self.assertEqual(evidence.repository_evidence, repository)
        with self.assertRaisesRegex(ValueError, "execution"):
            replace(evidence, execution_id="other")
        with self.assertRaisesRegex(ValueError, "unique"):
            replace(evidence, log_references=("log://run-1", "log://run-1"))


if __name__ == "__main__":
    unittest.main()
