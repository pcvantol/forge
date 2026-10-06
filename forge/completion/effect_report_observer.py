"""Forge interpretation of a verified EP effect report for approved criteria."""

from __future__ import annotations

import json
from typing import Any, Mapping

from forge.models.criterion_observation import CriterionObservation, canonical_digest
from forge.models.mission_completion import mission_criterion_id


def criterion_record(effect: Mapping[str, Any], criterion_id: str) -> dict[str, Any] | None:
    """Select one immutable criterion fact from the verified result projection."""
    criteria = effect.get("criteria")
    if not isinstance(criteria, list):
        return None
    matches = [item for item in criteria if isinstance(item, Mapping)
               and item.get("id") == criterion_id]
    if len(matches) != 1:
        return None
    item = matches[0]
    fields = ("contract_version", "mode", "delivery", "source_revision", "delivery_revision",
              "report_id", "report_digest", "source_manifest_digest", "subject_digest")
    if (effect.get("contract_version") != "1.0" or any(field not in effect for field in fields)
            or not isinstance(item.get("source_paths"), list) or not item["source_paths"]
            or not isinstance(item.get("analysis_digest"), str)):
        return None
    return {**{field: effect[field] for field in fields}, "criterion_id": criterion_id,
            "analysis_digest": item["analysis_digest"],
            "source_paths": item["source_paths"]}


def canonical_record(record: Mapping[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


class EffectReportCriterionObserver:
    """Observe only report requirements approved in the Mission contract."""

    def observe(self, mission, reference, evidence) -> tuple[CriterionObservation, ...]:
        effect = getattr(evidence, "effect_result", None)
        if not isinstance(effect, Mapping):
            return ()
        observations = []
        for contract in mission.criterion_assessment_contracts:
            criterion_id = mission_criterion_id(mission.id, contract.criterion)
            record = criterion_record(effect, criterion_id)
            if record is None or record["report_id"] != reference.report_id:
                continue
            for requirement in contract.requirements:
                if requirement.kind != "effect_report":
                    continue
                observations.append(CriterionObservation(
                    mission.id, canonical_digest(mission.to_dict()), criterion_id,
                    contract.digest, requirement.requirement_id, reference.receipt_id,
                    reference.action_id, reference.report_id, reference.repository_revision,
                    reference.repository_evidence_digest, "effect_report", reference.report_id,
                    "ep-effect-result", record["report_digest"], canonical_record(record),
                    "PASS", "VERIFIED_EP_EFFECT_CRITERION_SATISFIED",
                    requirement_digest=requirement.digest,
                    candidate_revision=reference.candidate_revision, schema_version="1.2",
                ))
        return tuple(observations)
