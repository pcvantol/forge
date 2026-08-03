"""Non-executing Business Advisor contract for Mission Candidate refinement."""

from __future__ import annotations

from dataclasses import dataclass

from forge.models.mission_candidate import MissionCandidate, MissionCandidateMaturity
from forge.models.mission_recommendation import RequiredDiscipline


@dataclass(frozen=True)
class BusinessAdvisorAdvice:
    candidate_id: str
    missing_information: tuple[str, ...]
    missing_disciplines: tuple[RequiredDiscipline, ...]
    assumption_challenges: tuple[str, ...]
    business_impact_assessment: str
    advisory: bool = True


class BusinessAdvisor:
    """Produces business advice only; it has no state, approval, Mission, or repository authority."""

    def advise(self, candidate: MissionCandidate) -> BusinessAdvisorAdvice:
        missing = []
        if candidate.maturity is not MissionCandidateMaturity.READY_FOR_ARCHITECTURE:
            missing.append("candidate maturity has not reached ready_for_architecture")
        if len(candidate.business_objective.split()) < 3:
            missing.append("business objective needs a concrete outcome")
        if len(candidate.dependencies) == 0:
            missing.append("dependencies need explicit confirmation, including none when applicable")
        disciplines = tuple(item for item in candidate.required_disciplines if item in {RequiredDiscipline.BUSINESS, RequiredDiscipline.COMMERCIAL, RequiredDiscipline.MARKET_RESEARCH, RequiredDiscipline.LEGAL, RequiredDiscipline.PRIVACY})
        challenges = ("Validate the stated business value against the target portfolio outcome.", "Confirm the priority against other Mission Candidates.")
        impact = f"Priority {candidate.priority}/100 with {candidate.confidence.value} confidence; review evidence before approval."
        return BusinessAdvisorAdvice(candidate.id, tuple(missing), disciplines, challenges, impact)
