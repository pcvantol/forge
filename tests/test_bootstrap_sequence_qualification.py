"""Regression coverage for the complete canonical bootstrap qualification."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.dispatcher import BOOTSTRAP_MISSION_SEQUENCE
from forge.runtime import RuntimeDatabase
from forge.qualification.bootstrap_sequence import (
    BootstrapQualificationInterrupted,
    load_canonical_bootstrap_portfolio,
    run_bootstrap_sequence_qualification,
)
from forge.scheduler.adapter import EngineeringPlatformInboxReceipt, EngineeringPlatformReport, EngineeringPlatformReportOutcome


class HostIssuedEvidenceSource:
    """Test-only stand-in for a separately owned Engineering Platform ledger."""

    def __init__(self, *, interrupt_after_submit: bool = False) -> None:
        self.receipts = {}; self.reports = {}; self.interrupt_after_submit = interrupt_after_submit; self.interrupted = False

    def submit(self, request):
        receipt = self.receipts.get(request.correlation_id)
        if receipt is None:
            suffix = f"{len(self.receipts) + 1:02d}"
            receipt = EngineeringPlatformInboxReceipt(f"host-run-{suffix}", f"host-receipt-{suffix}", request.execution_host_id, f"2026-08-04T12:00:{suffix}Z")
            self.receipts[request.correlation_id] = receipt
            self.reports[receipt.run_id] = EngineeringPlatformReport(
                receipt.run_id, f"host-report-{suffix}", EngineeringPlatformReportOutcome.COMPLETE,
                "qualification-revision", "sha256:" + "a" * 64, ("host:validation",), (),
                f"2026-08-04T12:00:{suffix}Z", f"2026-08-04T12:01:{suffix}Z", receipt.receipt_id,
                request.execution_host_id, request.correlation_id, request.runtime_prompt_id, request.mission_id,
                request.intent_id, request.intent_revision, request.action_id,
                execution_duration_ms=60_000,
            )
        if self.interrupt_after_submit and not self.interrupted:
            self.interrupted = True
            raise BootstrapQualificationInterrupted("controlled interruption after host-issued receipt")
        return receipt

    def receipt_for(self, correlation_id): return self.receipts.get(correlation_id)
    def report_for(self, run_id): return self.reports.get(run_id)


class BootstrapSequenceQualificationTests(unittest.TestCase):
    def test_executes_the_complete_fifo_portfolio_and_persists_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            report = run_bootstrap_sequence_qualification(Path(directory), HostIssuedEvidenceSource())
            database = RuntimeDatabase(root := Path(directory))
            self.addCleanup(database.close)
            evidence = database.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE)
            self.assertEqual(report.answer, "YES")
            self.assertEqual(report.dispatcher_status, "IDLE")
            self.assertEqual(report.mission_ids, BOOTSTRAP_MISSION_SEQUENCE)
            self.assertEqual([item["mission_id"] for item in evidence["missions"]], list(BOOTSTRAP_MISSION_SEQUENCE))
            self.assertTrue(all(item["qualified"] for item in evidence["missions"]))
            self.assertTrue(all(item["execution_receipts"] and item["architecture_reviews"] for item in evidence["missions"]))

    def test_resume_is_idempotent_after_complete_persisted_qualification(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory); source = HostIssuedEvidenceSource(); first = run_bootstrap_sequence_qualification(root, source)
            host_before = tuple(source.receipts.items())
            second = run_bootstrap_sequence_qualification(root, source)
            self.assertEqual(first, second)
            self.assertEqual(tuple(source.receipts.items()), host_before)

    def test_canonical_mission_definitions_drive_portfolio_not_generic_missions(self) -> None:
        portfolio = load_canonical_bootstrap_portfolio(Path(__file__).parents[1])
        self.assertEqual(tuple(item.identifier for item in portfolio), BOOTSTRAP_MISSION_SEQUENCE)
        self.assertEqual(portfolio[0].title, "Autonomous Engineering Foundation")
        self.assertIn("autonomously executing approved engineering Missions", portfolio[0].statement)
        self.assertNotEqual(portfolio[0].source_digest, portfolio[1].source_digest)

    def test_interruption_and_restart_preserve_completed_mission_evidence_and_fifo(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = HostIssuedEvidenceSource()
            with self.assertRaises(BootstrapQualificationInterrupted):
                run_bootstrap_sequence_qualification(root, source, interrupt_after_host_dispatch=True)
            self.assertEqual(len(source.receipts), 1)
            database = RuntimeDatabase(root)
            self.addCleanup(database.close)
            first = database.runtime_evidence().mission_qualification("MISSION-0001")
            self.assertTrue(first["qualified"])
            self.assertEqual(len(first["execution_receipts"]), 1)
            self.assertTrue(first["decision_evidence"])
            report = run_bootstrap_sequence_qualification(root, source)
            evidence = database.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE)
            self.assertEqual(report.dispatcher_status, "IDLE")
            self.assertEqual([item["mission_id"] for item in evidence["missions"]], list(BOOTSTRAP_MISSION_SEQUENCE))
            self.assertEqual(len(source.receipts), 5)
            self.assertEqual(len({item["execution_receipts"][0]["execution_run_id"] for item in evidence["missions"]}), 5)

    def test_json_evidence_cache_is_ignored_by_runtime_database_qualification(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bootstrap-sequence-evidence.json").write_text(json.dumps({
                "mission_sequence": list(BOOTSTRAP_MISSION_SEQUENCE), "dispatcher_status": "IDLE",
                "missions": [{"mission_id": identifier, "completion_outcome": "COMPLETED", "execution_evidence": {}, "execution_lineage": []} for identifier in BOOTSTRAP_MISSION_SEQUENCE],
            }), encoding="utf-8")
            report = run_bootstrap_sequence_qualification(root, HostIssuedEvidenceSource())
            self.assertEqual(report.answer, "YES")


if __name__ == "__main__":
    unittest.main()
