import json
import unittest
from copy import copy
from pathlib import Path

from forge.foundation import FoundationDocumentLoader
from forge.models import ProposalStatus, PromptArtifactStatus, transition_prompt_artifact, transition_proposal
from forge.planning import PlanningDocumentLoader
from forge.prompts import EngineeringPromptArtifactGenerator
from forge.proposals import EngineeringProposalGenerator


ROOT = Path(__file__).resolve().parents[1]


class EngineeringPromptArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        planning = json.loads((ROOT / "examples" / "planning.example.json").read_text())
        report = PlanningDocumentLoader({"engineering-kb"}).load(planning)
        assert report.document is not None
        self.planning = report.document
        foundation = FoundationDocumentLoader().load_path(ROOT / "examples" / "foundation.example.json")
        assert foundation.document is not None
        self.foundation = foundation.document
        proposal = EngineeringProposalGenerator().generate(
            proposal_id="planning-contracts-proposal", workspace=self.foundation.workspace, plan=self.planning.plans[0],
            goals=self.planning.goals, increment_proposals=self.planning.increment_proposals, increment_id="planning-contracts",
        )
        self.proposal = transition_proposal(transition_proposal(proposal, ProposalStatus.PROPOSED), ProposalStatus.APPROVED)

    def test_generator_creates_deterministic_portable_draft(self) -> None:
        artifact = EngineeringPromptArtifactGenerator().generate(
            artifact_id="planning-contracts-prompt", artifact_version="1", created_at="2026-07-31T00:00:00Z",
            proposal=self.proposal, workspace=self.foundation.workspace, repository=self.foundation.repositories[0],
            success_criteria=("Planning contracts validate deterministically.",),
            engineering_task_description="Implement the declared planning contracts.", validation_expectations=("Run focused planning tests.",),
            constraints=("Do not invoke a runtime provider or operate repositories.",), required_checks=("Focused planning tests pass.",),
            expected_evidence=("Deterministic test result.",), completion_criteria=("All required checks and evidence are present.",),
        )
        self.assertEqual(artifact.status, PromptArtifactStatus.DRAFT)
        self.assertEqual(artifact.context.repository_reference, "example/forge")
        self.assertEqual(artifact.to_dict(), json.loads((ROOT / "examples" / "engineering-prompt-artifact.example.json").read_text()))
        self.assertEqual(transition_prompt_artifact(artifact, PromptArtifactStatus.READY).status, PromptArtifactStatus.READY)
        self.assertEqual(artifact.to_markdown(), artifact.to_markdown())
        self.assertIn("Source Proposal: planning-contracts-proposal (v0.6)", artifact.to_markdown())
        self.assertIn("## Validation", artifact.to_markdown())

    def test_generator_requires_an_approved_proposal(self) -> None:
        draft = EngineeringProposalGenerator().generate(
            proposal_id="draft-proposal", workspace=self.foundation.workspace, plan=self.planning.plans[0], goals=self.planning.goals,
            increment_proposals=self.planning.increment_proposals, increment_id="planning-contracts",
        )
        with self.assertRaisesRegex(ValueError, "approved"):
            EngineeringPromptArtifactGenerator().generate(
                artifact_id="draft-prompt", artifact_version="1", created_at="2026-07-31T00:00:00Z", proposal=draft,
                workspace=self.foundation.workspace, repository=self.foundation.repositories[0], success_criteria=("criterion",),
                engineering_task_description="task", validation_expectations=(), constraints=(), required_checks=("check",),
                expected_evidence=("evidence",), completion_criteria=("complete",),
            )

    def test_generator_rejects_an_approved_proposal_without_evidence(self) -> None:
        invalid = copy(self.proposal)
        object.__setattr__(invalid, "evidence_references", ())
        with self.assertRaisesRegex(ValueError, "evidence"):
            EngineeringPromptArtifactGenerator().generate(
                artifact_id="invalid-prompt", artifact_version="1", created_at="2026-07-31T00:00:00Z",
                proposal=invalid, workspace=self.foundation.workspace, repository=self.foundation.repositories[0],
                success_criteria=("criterion",), engineering_task_description="task", validation_expectations=(),
                constraints=(), required_checks=("check",), expected_evidence=("evidence",), completion_criteria=("complete",),
            )


if __name__ == "__main__":
    unittest.main()
