"""Tests for the immutable, evidence-only Historical Engineering Intent model."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest

from forge.models import (
    HistoricalApproval,
    HistoricalBootstrapDocumentation,
    HistoricalEngineeringIntent,
    HistoricalEngineeringIntentStatus,
    HistoricalGovernanceStatus,
    HistoricalImplementationCommit,
    HistoricalImplementationReport,
    HistoricalProposal,
    HistoricalRepositoryEvidence,
)


def digest() -> str:
    return "sha256:" + "a" * 64


def historical_intent(**overrides: object) -> HistoricalEngineeringIntent:
    values: dict[str, object] = {
        "historical_id": "historical-bootstrap-001",
        "title": "Bootstrap knowledge capture",
        "objective": "Preserve pre-lifecycle engineering truth.",
        "bootstrap_milestone": "Bootstrap Milestone A",
        "reconstructed_at": "2026-08-01T12:00:00Z",
        "reconstruction_rationale": "The work predates Engineering Intent governance.",
        "repository_evidence": (HistoricalRepositoryEvidence("forge", "abc1234", "git://forge/abc1234", digest()),),
        "implementation_commits": (HistoricalImplementationCommit("forge", "abc1234", "git://forge/abc1234"),),
        "bootstrap_documentation": (HistoricalBootstrapDocumentation("bootstrap-milestone-a", "docs/reports/bootstrap-milestone-a.md", digest()),),
    }
    values.update(overrides)
    return HistoricalEngineeringIntent(**values)  # type: ignore[arg-type]


class HistoricalEngineeringIntentTests(unittest.TestCase):
    def test_valid_historical_intent_is_immutable_and_serializable(self) -> None:
        intent = historical_intent()
        document = intent.to_dict()
        self.assertEqual(intent.status, HistoricalEngineeringIntentStatus.HISTORICAL)
        self.assertEqual(document["proposal"]["status"], "HISTORICAL_NOT_AVAILABLE")
        self.assertEqual(document["approval"]["status"], "HISTORICAL_NOT_AVAILABLE")
        self.assertEqual(document["implementation_commits"][0]["commit_sha"], "abc1234")
        with self.assertRaises(FrozenInstanceError):
            intent.title = "rewritten history"  # type: ignore[misc]

    def test_proposal_and_approval_fabrication_are_prohibited(self) -> None:
        self.assertEqual({status.value for status in HistoricalGovernanceStatus}, {"HISTORICAL_NOT_AVAILABLE"})
        with self.assertRaisesRegex(ValueError, "proposal status"):
            HistoricalProposal("PROPOSED")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "approval status"):
            HistoricalApproval("APPROVED")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "governance"):
            historical_intent(proposal=object())

    def test_historical_evidence_requires_repository_bootstrap_and_direct_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "repository evidence"):
            historical_intent(repository_evidence=())
        with self.assertRaisesRegex(ValueError, "bootstrap documentation"):
            historical_intent(bootstrap_documentation=())
        with self.assertRaisesRegex(ValueError, "implementation commit or implementation report"):
            historical_intent(implementation_commits=())
        report_only = historical_intent(
            implementation_commits=(),
            implementation_reports=(HistoricalImplementationReport("report-001", "docs/reports/report.md", digest()),),
        )
        self.assertEqual(report_only.implementation_reports[0].report_id, "report-001")

    def test_historical_status_is_fixed_and_has_no_lifecycle_transition(self) -> None:
        with self.assertRaisesRegex(ValueError, "status"):
            historical_intent(status="VERIFIED")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "timestamp"):
            historical_intent(reconstructed_at="2026-08-01")
        self.assertEqual(replace(historical_intent()).status, HistoricalEngineeringIntentStatus.HISTORICAL)


if __name__ == "__main__":
    unittest.main()
