"""Focused regression coverage for the Forge-owned Business Governance Ingress."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import inspect

from forge.business import BusinessGovernanceIngress
from forge.governance import resolve_governance_profile
from forge.lifecycle import MissionRecommendation, RecommendationLifecycleStore, RecommendationStatus
from forge.mission_scheduler import MissionRuntimeScheduler, SubmissionAcceptance
from forge.runtime import RuntimeDatabase


def recommendation(identifier: str = "project-intelligence-foundation") -> MissionRecommendation:
    return MissionRecommendation(
        id=identifier, title="Project Intelligence Foundation", mission_origin="portfolio_intelligence",
        business_summary="Make portfolio intelligence a governed Mission capability.",
        engineering_summary="Implement the bounded Project Intelligence foundation.",
        business_value="Improves governed prioritisation.", engineering_value="Creates reusable intelligence inputs.",
        architectural_value="Preserves the canonical governance boundary.",
        repository_evidence=("repository:forge",), decision_evidence_reference="review:project-intelligence",
        dependencies=("none-confirmed",), alternatives=("Defer the foundation.",), confidence=90,
        recommendation_timestamp="2026-08-15T20:00:00Z",
    )


class Inbox:
    def __init__(self): self.envelopes = []
    def submit(self, envelope):
        self.envelopes.append(envelope)
        return SubmissionAcceptance(envelope["submission_id"], "host-run-1")


class BusinessGovernanceIngressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory(); root = Path(self.directory.name)
        self.lifecycle = RecommendationLifecycleStore(root / "governance.sqlite")
        self.runtime = RuntimeDatabase(root, forge_version="test")
        self.addCleanup(self.lifecycle.close); self.addCleanup(self.runtime.close); self.addCleanup(self.directory.cleanup)
        self.lifecycle.create_recommendation(recommendation(), actor="portfolio", rationale="Canonical recommendation.")
        self.lifecycle.transition("project-intelligence-foundation", RecommendationStatus.RECOMMENDED,
                                  actor="portfolio", occurred_at="2026-08-15T20:01:00Z", rationale="Ready for review.")

    def ingress(self, scheduler=None):
        return BusinessGovernanceIngress(self.lifecycle, self.runtime, resolve_governance_profile("solo"), scheduler=scheduler)

    def test_not_found_and_authorization_fail_closed_without_state_mutation(self) -> None:
        self.assertEqual(self.ingress().approve_recommendation("missing", actor="primary_operator", occurred_at="now", rationale="Approve.").result, "NOT_FOUND")
        self.assertEqual(self.ingress().approve_recommendation("project-intelligence-foundation", actor=None, occurred_at="now", rationale="Approve.").result, "AUTHORIZATION_REQUIRED")
        self.assertEqual(self.ingress().approve_recommendation("project-intelligence-foundation", actor="other", occurred_at="now", rationale="Approve.").result, "FORBIDDEN")
        self.assertEqual(self.lifecycle.get_recommendation("project-intelligence-foundation").status, RecommendationStatus.RECOMMENDED)

    def test_ambiguous_canonical_title_fails_closed(self) -> None:
        duplicate = recommendation("project-intelligence-foundation-2")
        self.lifecycle.create_recommendation(duplicate, actor="portfolio", rationale="Separate canonical record.")
        self.lifecycle.transition(duplicate.id, RecommendationStatus.RECOMMENDED, actor="portfolio", occurred_at="2026-08-15T20:01:00Z", rationale="Ready.")
        result = self.ingress().approve_recommendation("Project Intelligence Foundation", actor="primary_operator", occurred_at="now", rationale="No inference.")
        self.assertEqual(result.result, "AMBIGUOUS")
        self.assertEqual(self.lifecycle.get_recommendation("project-intelligence-foundation").status, RecommendationStatus.RECOMMENDED)

    def test_business_approval_is_idempotent_and_pauses_for_architecture(self) -> None:
        first = self.ingress().approve_recommendation("project-intelligence-foundation", actor="primary_operator", occurred_at="2026-08-15T20:02:00Z", rationale="Business value approved.")
        again = self.ingress().approve_recommendation("project-intelligence-foundation", actor="primary_operator", occurred_at="2026-08-15T20:03:00Z", rationale="Retry.")
        self.assertEqual((first.result, again.result), ("WAITING_ARCHITECTURE_APPROVAL", "WAITING_ARCHITECTURE_APPROVAL"))
        self.assertEqual(first.business_decision_id, again.business_decision_id)
        self.assertEqual(len([item for item in self.lifecycle.history("project-intelligence-foundation") if item.kind == "business_decision"]), 1)

    def test_architecture_approval_reuses_governance_and_scheduler_owns_forge_submission(self) -> None:
        self.ingress().approve_recommendation("project-intelligence-foundation", actor="primary_operator", occurred_at="2026-08-15T20:02:00Z", rationale="Business value approved.")
        self.lifecycle.transition("project-intelligence-foundation", RecommendationStatus.ARCHITECTURE_APPROVED,
                                  actor="primary_operator", occurred_at="2026-08-15T20:03:00Z", rationale="Architecture approved.")
        inbox = Inbox(); scheduler = MissionRuntimeScheduler(self.runtime, inbox, timestamp="2026-08-15T20:04:00Z")
        result = self.ingress(scheduler).approve_recommendation("project-intelligence-foundation", actor="primary_operator", occurred_at="2026-08-15T20:04:00Z", rationale="Reconcile approval.")
        repeated = self.ingress(scheduler).approve_recommendation("project-intelligence-foundation", actor="primary_operator", occurred_at="2026-08-15T20:05:00Z", rationale="Restart recovery.")
        self.assertEqual(result.result, "APPROVED_AND_ACTIVATED")
        self.assertEqual((result.architecture_state, result.mission_runtime_state, result.scheduler_state), ("ARCHITECTURE_APPROVED", "ACTIVE", "WAITING_EXECUTION"))
        self.assertEqual(result.mission_id, repeated.mission_id)
        self.assertEqual(len(inbox.envelopes), 1)
        self.assertEqual(inbox.envelopes[0]["producer"]["type"], "FORGE")
        self.assertIn("execution_context", inbox.envelopes[0])
        self.assertEqual(self.lifecycle.get_recommendation("project-intelligence-foundation").status, RecommendationStatus.MISSION_ALLOCATED)

    def test_terminal_recommendation_states_fail_closed(self) -> None:
        self.lifecycle.transition("project-intelligence-foundation", RecommendationStatus.SUPERSEDED,
                                  actor="portfolio", occurred_at="2026-08-15T20:02:00Z", rationale="Superseded.")
        result = self.ingress().approve_recommendation("project-intelligence-foundation", actor="primary_operator", occurred_at="2026-08-15T20:03:00Z", rationale="No bypass.")
        self.assertEqual(result.result, "INVALID_LIFECYCLE_STATE")

    def test_ingress_uses_canonical_boundaries_without_execution_host_or_local_scheduler(self) -> None:
        source = inspect.getsource(BusinessGovernanceIngress)
        self.assertNotIn("engineering_platform", source)
        self.assertNotIn("inbox", source.lower())
        self.assertNotIn("codex", source.lower())
        self.assertNotIn("class MissionRuntimeScheduler", source)


if __name__ == "__main__": unittest.main()
