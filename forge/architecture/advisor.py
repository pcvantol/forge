"""Immutable, non-executing Architecture Advisor contract."""

from __future__ import annotations

from dataclasses import dataclass

from forge.models.architecture_mission import ArchitectureMission


@dataclass(frozen=True)
class ArchitectureAdvisorAdvice:
    mission_id: str
    technical_feasibility: str
    architecture_consistency: str
    implementation_boundaries: tuple[str, ...]
    dependency_findings: tuple[str, ...]
    risk_findings: tuple[str, ...]
    repository_consistency: str
    capability_reuse: tuple[str, ...]
    governance_compliance: str
    advisory: bool = True


class ArchitectureAdvisor:
    """Produces advice only; it cannot approve, plan, execute, or operate a repository."""

    def advise(self, mission: ArchitectureMission) -> ArchitectureAdvisorAdvice:
        readiness = "ready for engineering approval" if mission.is_engineering_ready() else "requires architectural refinement before engineering approval"
        boundaries = mission.engineering_constraints or ("Define explicit engineering constraints.",)
        dependencies = tuple(f"Review dependency: {item}" for item in mission.dependencies) or ("Identify dependencies.",)
        risks = tuple(f"Review risk: {item}" for item in mission.risks) or ("Identify technical risks.",)
        capabilities = tuple(f"Assess reuse of capability: {item}" for item in mission.required_capabilities) or ("Assess existing capability reuse.",)
        return ArchitectureAdvisorAdvice(
            mission.id, readiness, "Preserve the approved business objective and Mission boundaries.", boundaries,
            dependencies, risks, "Repository truth must be reviewed by a human; this contract performs no repository access.",
            capabilities, "Architecture approval remains a Platform Architect decision.",
        )
