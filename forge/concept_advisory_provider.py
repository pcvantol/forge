"""Briefing schema/prompt specialization of the existing provider and permits."""
import json
from .advisory_provider import AdvisoryProvider, AdvisoryProviderUnavailable, INSTRUCTIONS
from .advisory_contract import AdvisoryConflict, digest
from .concept_advisory_contract import CONTRACT, OUTPUT_SCHEMA, result
from .planner.codex_cli_session import _policy_digest


class ConceptAdvisoryProvider(AdvisoryProvider):
    contract = CONTRACT
    output_schema = OUTPUT_SCHEMA
    instructions = INSTRUCTIONS + '''\nWork only with the explicitly supplied pre-project briefing and prior accepted
turns. Preserve unknown information. Answer in the requested language. Distinguish
assumptions and questions from supplied facts. Changes are proposals for the six
briefing fields only, with exact before-values and supplied source references.
Business/Architecture advice is not approval. No project registration or effects.'''

    def validate_output(self, document, admitted):
        return result(document, admitted)

    def prepare(self, admitted, history):
        try:
            policy = self.configuration.current_policy()
        except PermissionError as error:
            raise AdvisoryProviderUnavailable('current session policy unavailable') from error
        if not policy.provider_home or not policy.provider_config_home or policy.instance_id != admitted['request']['instance_id']:
            raise AdvisoryProviderUnavailable('instance-owned provider context required')
        if self.configuration.policy_service.db._connection.execute("SELECT 1 FROM planning_provider_generation_permits WHERE state IN ('PENDING','TRANSPORT_COMMITTED') LIMIT 1").fetchone():
            raise AdvisoryConflict('INVOCATION_UNRESOLVED')
        prompt = {'contract_version': self.contract, 'request': admitted['request'],
                  'request_digest': admitted['request_digest'], 'context': admitted['context'],
                  'session_id': admitted['session_id'], 'invocation_id': admitted['invocation_id'],
                  'prior_turns': history}
        binding = {'request': prompt, 'schema': self.output_schema,
                   'instructions': self.instructions, 'policy_digest': _policy_digest(policy)}
        if len(json.dumps(binding).encode()) > min(policy.input_token_bound, policy.context_token_bound):
            raise ValueError('finite concept context exceeds configured bounds')
        return policy, prompt, digest(binding)
