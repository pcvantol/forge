import json
import unittest
from pathlib import Path

from forge.models import ProposalStatus, transition_proposal
from forge.foundation import FoundationDocumentLoader
from forge.planning import PlanningDocumentLoader
from forge.proposals import EngineeringProposalGenerator


ROOT = Path(__file__).resolve().parents[1]


class EngineeringProposalGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        planning = json.loads((ROOT / "examples" / "planning.example.json").read_text())
        report = PlanningDocumentLoader({"engineering-kb"}).load(planning)
        assert report.document is not None
        self.document = report.document
        foundation = FoundationDocumentLoader().load_path(ROOT / "examples" / "foundation.example.json")
        assert foundation.document is not None
        self.workspace = foundation.document.workspace
        self.generator = EngineeringProposalGenerator()

    def test_generator_creates_deterministic_traceable_draft(self) -> None:
        proposal = self.generator.generate(
            proposal_id="planning-contracts-proposal",
            workspace=self.workspace,
            plan=self.document.plans[0],
            goals=self.document.goals,
            increment_proposals=self.document.increment_proposals,
            increment_id="planning-contracts",
        )
        self.assertEqual(proposal.status, ProposalStatus.DRAFT)
        self.assertEqual(proposal.creation_metadata.source_plan_id, "planning-foundation-plan")
        self.assertEqual(proposal.scope.affected_capabilities, ("engineering-planning",))
        self.assertEqual(len(proposal.evidence_references), 2)
        self.assertEqual(proposal.to_dict(), json.loads((ROOT / "examples" / "engineering-proposal.example.json").read_text()))

    def test_generator_requires_plan_goal_and_increment_context(self) -> None:
        with self.assertRaisesRegex(ValueError, "ordered"):
            self.generator.generate(
                proposal_id="planning-contracts-proposal",
                workspace=self.workspace,
                plan=self.document.plans[0], goals=self.document.goals,
                increment_proposals=self.document.increment_proposals,
                increment_id="missing-increment",
            )

    def test_lifecycle_changes_are_explicit_and_ordered(self) -> None:
        proposal = self.generator.generate(
            proposal_id="planning-contracts-proposal", plan=self.document.plans[0], goals=self.document.goals,
            workspace=self.workspace,
            increment_proposals=self.document.increment_proposals, increment_id="planning-contracts",
        )
        proposed = transition_proposal(proposal, ProposalStatus.PROPOSED)
        approved = transition_proposal(proposed, ProposalStatus.APPROVED)
        self.assertEqual(transition_proposal(approved, ProposalStatus.EXECUTED).status, ProposalStatus.EXECUTED)
        with self.assertRaises(ValueError):
            transition_proposal(proposal, ProposalStatus.APPROVED)


if __name__ == "__main__":
    unittest.main()
