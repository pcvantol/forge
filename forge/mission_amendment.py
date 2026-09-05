"""Append-only governed amendments for APPROVED_PLANNABLE Missions."""
from __future__ import annotations
from hashlib import sha256
import json
from forge.governance_authority import CanonicalGovernanceRepository, GovernanceCapability

def _digest(value): return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

class MissionAmendmentService:
    def __init__(self, repository: CanonicalGovernanceRepository): self.repository = repository
    def effective_contract(self, mission_id):
        state=self.repository.database.get_document("mission_state", mission_id); contract=state.get("admission_contract")
        if state.get("status") != "APPROVED_PLANNABLE" or not isinstance(contract,dict): raise ValueError("only approved/plannable canonical Missions may be amended")
        effective={**contract, "mission": dict(contract["mission"])}; predecessor=_digest(contract)
        rows=self.repository.database._connection.execute("SELECT document FROM mission_amendments WHERE mission_id=? ORDER BY revision",(mission_id,)).fetchall()
        for row in rows:
            amendment=json.loads(row["document"])
            if amendment["predecessor_digest"] != predecessor: raise ValueError("stale or conflicting amendment lineage")
            effective["mission"]["engineering_constraints"] = sorted(set(effective["mission"].get("engineering_constraints",())) | set(amendment["changed_fields"].get("engineering_constraints_add",())))
            predecessor=amendment["effective_contract_digest"]
        return effective, predecessor
    def amend_no_repository_target(self, mission_id, *, business_decision_id, architecture_decision_id, rationale, context):
        if not self.repository.operators.authorize(context): raise PermissionError("trusted operator context is required")
        effective, predecessor=self.effective_contract(mission_id)
        if "NO_REPOSITORY_TARGET=TRUE" in effective["mission"].get("engineering_constraints",()): raise ValueError("no-repository-target is already effective")
        for identifier, capability in ((business_decision_id,GovernanceCapability.BUSINESS_APPROVAL),(architecture_decision_id,GovernanceCapability.ARCHITECTURE_APPROVAL)):
            decision=self.repository.decision(identifier)
            if decision["capability"] != capability.value or decision["decision"] != "approved" or decision["subject_id"] != mission_id:
                raise PermissionError("amendment requires canonical approved Business and Architecture decisions for its Mission")
        revision=self.repository.database._connection.execute("SELECT COALESCE(MAX(revision),0)+1 FROM mission_amendments WHERE mission_id=?",(mission_id,)).fetchone()[0]
        changed={"engineering_constraints_add":["NO_REPOSITORY_TARGET=TRUE"]}
        base={"amendment_id":f"{mission_id}:amendment:{revision}","mission_id":mission_id,"revision":revision,"predecessor_digest":predecessor,"changed_fields":changed,"rationale":rationale,"installation_id":effective["installation_id"],"business_decision_id":business_decision_id,"architecture_decision_id":architecture_decision_id}
        effective["mission"]["engineering_constraints"] = sorted(set(effective["mission"].get("engineering_constraints",())) | {"NO_REPOSITORY_TARGET=TRUE"})
        base["effective_contract_digest"]=_digest(effective); base["digest"]=_digest(base)
        return self.repository.database.create_mission_amendment(base)
