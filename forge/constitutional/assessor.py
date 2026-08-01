"""Pure deterministic assessment of declared Constitutional Validation input."""

from __future__ import annotations

from collections.abc import Iterable

from forge.models import (
    ConstitutionalAssessment,
    ConstitutionalAssessmentStatus,
    ConstitutionalFinding,
    ConstitutionalFindingSeverity,
    ConstitutionalRule,
)


class ConstitutionalAssessor:
    """Assess supplied architectural findings; never retrieve, enforce, or mutate."""

    def assess(
        self,
        subject_id: str,
        applicable_rules: Iterable[ConstitutionalRule],
        findings: Iterable[ConstitutionalFinding],
    ) -> ConstitutionalAssessment:
        """Derive an assessment with fixed severity precedence and stable ordering."""
        rules = tuple(sorted(applicable_rules))
        ordered_findings = tuple(sorted(findings))
        if not rules:
            if ordered_findings:
                raise ValueError("constitutional findings require at least one applicable rule")
            status = ConstitutionalAssessmentStatus.NOT_APPLICABLE
        elif any(finding.severity is ConstitutionalFindingSeverity.VIOLATION for finding in ordered_findings):
            status = ConstitutionalAssessmentStatus.VIOLATION
        elif ordered_findings:
            status = ConstitutionalAssessmentStatus.WARNING
        else:
            status = ConstitutionalAssessmentStatus.PASS
        return ConstitutionalAssessment(subject_id, rules, status, ordered_findings)
