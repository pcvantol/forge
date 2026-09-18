"""Public source-runtime recovery retains failures while deriving a valid successor."""
from dataclasses import replace
import tests.test_installed_dynamic_mission_runtime as fixture
import unittest
_digest = fixture._digest
from tests.criterion_fixture import ExactRepositoryBytes
from forge.execution import RecoveryAuthorization
from forge.models.action_derivation import DerivedActionProposal, ProposalProvenance, ProviderInvocationEvidence, ProviderSideEffectState, MissionGapBinding, MissionGapClassification
from forge.models.execution_host import ExecutionEvidenceOutcome
from forge.planner.provider_adapter import ProviderDerivationResponse

class Provider(fixture._Provider):
    def derive_with_planning_input(self,snapshot,_planning_input,_policy,*,derivation_id,attempt_authority_id=None,durable_attempt_specification=None,durable_result_sink=None):
        self.calls+=1
        successor=self.calls>1
        action_id='successor-action' if successor else 'status-projection-action'
        objective='Deliver corrected approved structural JSON.' if successor else 'Deliver initial structural JSON.'
        refs=tuple(item.source_id for item in snapshot.evidence)
        gap=None if not successor else MissionGapBinding(MissionGapClassification.UNPROVEN_MISSION_CRITERION,tuple(item.criterion_id for item in snapshot.criteria),refs,snapshot.digest,objective,())
        proposal=DerivedActionProposal(action_id,'durable-status-projection',objective,(),('forge/__main__.py',),(objective,),('python -m unittest',),1,False,('protected-delivery',),('scope-drift',),ProposalProvenance(derivation_id,snapshot.id,snapshot.digest,'fixture-v1','fixture',None,refs),gap)
        response=ProviderDerivationResponse(ProviderInvocationEvidence('fixture',None,'fixture-v1',durable_attempt_specification['derivation_request_digest'],snapshot.digest,_digest({'derivation':derivation_id}),ProviderSideEffectState.HAPPENED_AND_CONFIRMED,status='completed'),proposals=(proposal,))
        durable_result_sink(response)
        return (proposal,)

class Host(fixture._Host):
    def retrieve_evidence(self,dispatch):
        if dispatch.request.action_id=='successor-action':
            return None
        return super().retrieve_evidence(dispatch)


class RecoveredPartialCompletionTests(unittest.TestCase):
    def test_authorized_retry_partial_completion_derives_and_dispatches_successor(self):
        f=fixture.InstalledDynamicMissionRuntimeTests();f.setUp()
        try:
            f.provider=Provider();f.host=Host()
            f.runtime.provider=f.provider;f.runtime.host=f.host
            f.runtime._criterion_observer.reader=ExactRepositoryBytes('synthetic/forge','c'*40,{'contract.json':b'{"source":"incorrect-source"}'})
            mission,envelope=f._mission_and_envelope()
            f.runtime.admit(mission,envelope)
            assert f.runtime.start(mission.id,f._truth()).status=='WAITING_FOR_EVIDENCE'
            f.host.return_evidence=True;f.host.outcome=ExecutionEvidenceOutcome.FAILED
            assert f.runtime.resume(mission.id).status=='FAILED'
            f.host.outcome=ExecutionEvidenceOutcome.COMPLETE
            result=f.runtime.recover(mission.id,RecoveryAuthorization(mission.id,'status-projection-action','synthetic-recovery','Retry the approved initial Action once.'))
            state=f.runtime.states.get(mission.id)
            assert result.status=='WAITING_FOR_EVIDENCE'
            assert len(f.host.requests)==3 and f.provider.calls==2
            assert [item['outcome'] for item in state.execution_history]==['failed','complete']
            assert len(state.actions)==2
        finally:
            f.tearDown()
