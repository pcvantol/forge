"""Read-only Generation 1 Bootstrap qualification regressions."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.qualification import qualify_generation_one_bootstrap
from forge.qualification.bootstrap_sequence import run_bootstrap_sequence_qualification
from forge.runtime import RuntimeDatabase
from forge.scheduler.adapter import EngineeringPlatformInboxReceipt, EngineeringPlatformReport, EngineeringPlatformReportOutcome


class _HostEvidence:
    """External evidence fixture used only to seed a completed runtime database."""

    def __init__(self) -> None:
        self.receipts = {}
        self.reports = {}

    def submit(self, request):
        receipt = self.receipts.get(request.correlation_id)
        if receipt is None:
            suffix = f"{len(self.receipts) + 1:02d}"
            receipt = EngineeringPlatformInboxReceipt(f"run-{suffix}", f"receipt-{suffix}", request.execution_host_id, f"2026-08-05T00:00:{suffix}Z")
            self.receipts[request.correlation_id] = receipt
            self.reports[receipt.run_id] = EngineeringPlatformReport(receipt.run_id, f"report-{suffix}", EngineeringPlatformReportOutcome.COMPLETE, "revision", "sha256:" + "b" * 64, (), (), f"2026-08-05T00:00:{suffix}Z", f"2026-08-05T00:01:{suffix}Z", receipt.receipt_id, request.execution_host_id, request.correlation_id, request.runtime_prompt_id, request.mission_id, request.intent_id, request.intent_revision, request.action_id, execution_duration_ms=60_000)
        return receipt

    def receipt_for(self, correlation_id):
        return self.receipts.get(correlation_id)

    def report_for(self, run_id):
        return self.reports.get(run_id)

    def resolves(self, *, execution_host, execution_run_id, engineering_report_id,
                 correlation_identity, executed_at, outcome):
        receipt = next((item for item in self.receipts.values()
                        if item.run_id == execution_run_id and item.host_id == execution_host), None)
        report = self.reports.get(execution_run_id)
        return bool(receipt and report and report.report_id == engineering_report_id
                    and report.correlation_id == correlation_identity
                    and report.execution_completed_at == executed_at
                    and report.outcome.value.lower() == outcome)


class GenerationOneBootstrapQualificationTests(unittest.TestCase):
    def test_projects_an_existing_runtime_database_without_dispatching(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = _HostEvidence()
            run_bootstrap_sequence_qualification(root, source)
            database = RuntimeDatabase(root)
            self.addCleanup(database.close)
            report = qualify_generation_one_bootstrap(database, source)
            self.assertEqual(report.answer, "YES")
            self.assertEqual(report.recommended_next_increment, "Generation 1 Completion Record")
            self.assertEqual(report.projection["source"], "runtime_database")
            self.assertEqual(report.projection["dispatcher_status"], "IDLE")
            self.assertFalse(report.missing_runtime_evidence)
            self.assertEqual(len(source.receipts), 5)

    def test_requires_independent_engineering_platform_receipt_resolution(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = _HostEvidence()
            run_bootstrap_sequence_qualification(root, source)
            database = RuntimeDatabase(root)
            self.addCleanup(database.close)
            report = qualify_generation_one_bootstrap(database)
            self.assertEqual(report.answer, "NO")
            self.assertIn("MISSION-0001:engineering_platform_evidence", report.missing_runtime_evidence)

    def test_empty_instance_identifies_every_missing_bootstrap_mission(self) -> None:
        with TemporaryDirectory() as directory:
            database = RuntimeDatabase(Path(directory))
            self.addCleanup(database.close)
            report = qualify_generation_one_bootstrap(database)
            self.assertEqual(report.answer, "NO")
            for mission_id in ("MISSION-0001", "MISSION-0002", "MISSION-0003", "MISSION-0004", "MISSION-0005"):
                self.assertIn(f"{mission_id}:mission_state", report.missing_runtime_evidence)

    def test_reads_the_portfolio_only_from_the_persisted_runtime_instance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_bootstrap_sequence_qualification(root, _HostEvidence())
            database = RuntimeDatabase(root)
            self.addCleanup(database.close)
            persisted = database.runtime_evidence().bootstrap_qualification()
            self.assertEqual(persisted["mission_ids"], (
                "MISSION-0001", "MISSION-0002", "MISSION-0003", "MISSION-0004", "MISSION-0005",
            ))

    def test_fails_closed_with_exact_missing_runtime_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            database = RuntimeDatabase(Path(directory))
            self.addCleanup(database.close)
            report = qualify_generation_one_bootstrap(database)
            self.assertEqual(report.answer, "NO")
            self.assertIsNone(report.recommended_next_increment)
            self.assertIn("dispatcher:bootstrap_fifo_sequence", report.missing_runtime_evidence)
            self.assertIn("dispatcher:idle", report.missing_runtime_evidence)
            self.assertIn("approved_mission_queue:empty", report.missing_runtime_evidence)


if __name__ == "__main__":
    unittest.main()
