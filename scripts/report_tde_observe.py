#!/usr/bin/env python3
"""Expose Forge's nonblocking TDE evidence without changing its decision."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Any


_DECISIONS = frozenset({"PASS", "PASS_WITH_WARNINGS", "FAIL"})
_QUALIFICATIONS = frozenset({"QUALIFIED", "FAILED"})
_EXIT = re.compile(r"(?:0|[1-9][0-9]{0,2})\Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _field(value: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _decision(value: object) -> str:
    return value if isinstance(value, str) and value in _DECISIONS else "UNAVAILABLE"


def _exit_codes(path: Path) -> tuple[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return "UNAVAILABLE", "UNAVAILABLE"
    entries: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {"assessment_exit", "qualification_exit"}:
            if key in entries or not _EXIT.fullmatch(value):
                entries[key] = "UNAVAILABLE"
            else:
                entries[key] = value
    return entries.get("assessment_exit", "UNAVAILABLE"), entries.get("qualification_exit", "UNAVAILABLE")


def report(evidence_dir: Path) -> tuple[str, bool]:
    """Return a bounded job summary and whether the operator needs a warning."""
    assessment = _read_json(evidence_dir / "assessment.json")
    qualification = _read_json(evidence_dir / "qualification.json")
    assessment_decision = _decision(_field(assessment, "evidence", "assessment", "assessmentDecision"))
    policy_decision = _decision(_field(assessment, "qualification", "policyDecision"))
    if assessment_decision != policy_decision:
        assessment_decision = "UNAVAILABLE"
    repository_decision = _decision(_field(qualification, "repositoryQualification", "assessmentDecision"))
    repository_status = _field(qualification, "repositoryQualification", "qualificationStatus")
    if not isinstance(repository_status, str) or repository_status not in _QUALIFICATIONS:
        repository_status = "UNAVAILABLE"
    rules = _field(assessment, "qualification", "triggeredRules")
    rule_count = str(len(rules)) if isinstance(rules, list) and all(isinstance(item, dict) for item in rules) else "UNAVAILABLE"
    assessment_exit, qualification_exit = _exit_codes(evidence_dir / "summary.txt")
    healthy = (assessment_decision == "PASS" and repository_decision == "PASS"
               and repository_status == "QUALIFIED" and rule_count == "0"
               and assessment_exit == "0" and qualification_exit == "0")
    summary = "\n".join((
        "## Forge TDE observe readback",
        "",
        "This workflow is nonblocking. Its successful completion is not a TDE assessment PASS.",
        "",
        "| Evidence | Result |",
        "| --- | --- |",
        f"| Assessment decision | `{assessment_decision}` |",
        f"| Repository assessment decision | `{repository_decision}` |",
        f"| Repository qualification | `{repository_status}` |",
        f"| Triggered policy rules | `{rule_count}` |",
        f"| Assessment command exit | `{assessment_exit}` |",
        f"| Qualification command exit | `{qualification_exit}` |",
        "",
        "See the `tde-observe-evidence` artifact for the detailed canonical evidence.",
        "",
    ))
    return summary, not healthy


def main() -> int:
    evidence_dir = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("tde-observe")
    summary, warning = report(evidence_dir)
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with Path(destination).open("a", encoding="utf-8") as output:
            output.write(summary)
    else:
        print(summary, end="")
    if warning:
        print("::warning title=TDE observe evidence::Assessment or repository qualification is failing or unavailable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
