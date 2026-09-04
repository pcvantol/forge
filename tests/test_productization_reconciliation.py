"""Semantic guardrails for the canonical productization reconciliation."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
DOCUMENT = ROOT / "docs/architecture/FORGE_PRODUCTIZATION_RECONCILIATION.md"


class ProductizationReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = DOCUMENT.read_text(encoding="utf-8")

    def test_preserves_governed_lifecycle_order(self) -> None:
        lifecycle = self.text.split("## Product lifecycle", 1)[1].split("## Refinement", 1)[0]
        expected = (
            "Product Vision -> Portfolio -> Mission Candidate -> Business Review\n"
            "-> Approved for Architecture -> Architecture Review -> Approved for Engineering\n"
            "-> Mission -> Engineering -> Execution -> Evidence -> Architecture Review\n"
            "-> Mission Recommendation -> Portfolio"
        )
        self.assertIn(expected, lifecycle)
        for invariant in (
            "MISSION_CANDIDATE_IS_NOT_EXECUTABLE = TRUE",
            "MISSION_RECOMMENDATION_IS_ADVISORY = TRUE",
            "BUSINESS_APPROVAL_REMAINS_EXPLICIT = TRUE",
            "ARCHITECTURE_APPROVAL_REMAINS_EXPLICIT = TRUE",
            "FORGE_AUTONOMY_BEGINS_ONLY_INSIDE_APPROVED_MISSION = TRUE",
        ):
            self.assertIn(invariant, lifecycle)

    def test_authority_and_state_matrices_cover_required_concepts_once(self) -> None:
        authority = self.text.split("## Target authority matrix", 1)[1].split("## State and projection matrix", 1)[0]
        state = self.text.split("## State and projection matrix", 1)[1].split("## Supersession", 1)[0]
        authority_rows = {line.split("|")[1].strip() for line in authority.splitlines() if line.startswith("| ")}
        state_rows = {line.split("|")[1].strip() for line in state.splitlines() if line.startswith("| ")}
        for concept in (
            "Product Vision", "Portfolio", "Forecast", "Mission Candidate",
            "Business refinement", "Business approval", "Architecture refinement",
            "Architecture approval", "Mission", "Roadmap DAG", "Living Mission Graph",
            "Engineering Action", "Submission", "Run", "Execution Receipt",
            "Quality Learning", "Knowledge Learning", "Workspace presentation", "CLI", "MCP",
        ):
            self.assertIn(concept, authority_rows)
        for concept in (
            "Product Vision", "Portfolio", "Forecast", "Mission Candidate",
            "Architecture Mission", "Mission Runtime", "Roadmap DAG",
            "Living Mission Graph", "Quality Learning", "Knowledge Learning",
        ):
            self.assertIn(concept, state_rows)
        self.assertIn("AUTHORITY_CONFLICT_COUNT = 0", authority)
        self.assertIn("UNCLASSIFIED_FIRST_CLASS_STATE = 0", state)

    def test_adapters_and_graph_do_not_create_new_authority(self) -> None:
        for invariant in (
            "CLI_IS_NOT_SECOND_AUTHORITY = TRUE",
            "WORKSPACE_DOES_NOT_SHELL_OUT_TO_FORGE_CLI = TRUE",
            "MCP_IS_ADAPTER_NOT_AUTHORITY = TRUE",
            "FORGE_DOES_NOT_CALL_ITSELF_THROUGH_MCP = TRUE",
            "ROADMAP_DAG_IS_NOT_LIVING_MISSION_GRAPH = TRUE",
            "MISSION_GRAPH_CANNOT_CHANGE_APPROVED_MISSION_BOUNDARY = TRUE",
            "V1_IMPLEMENTATION_DEPENDENCY_CYCLES = 0",
        ):
            self.assertIn(invariant, self.text)


if __name__ == "__main__":
    unittest.main()
