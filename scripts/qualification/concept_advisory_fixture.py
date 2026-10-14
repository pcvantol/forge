"""Explicit synthetic external-provider boundary, never live advice qualification."""
import json
import sys
from pathlib import Path
from datetime import UTC, datetime, timedelta

EXTERNAL = '''#!PYTHON
import json,sys,os,time
from pathlib import Path
ROOT=Path(ROOT_LITERAL)
a=sys.argv[1:]
if '--version' in a:print('codex-cli 0.153.0');sys.exit(0)
if a[-2:]==['login','status']:print('Logged in using ChatGPT');sys.exit(0)
assert '--ephemeral' in a and '--sandbox' in a and a[a.index('--sandbox')+1]=='read-only'
assert '--ignore-rules' in a and '--ignore-user-config' in a
v=json.loads(sys.stdin.read());assert v['contract_version']=='forge-preproject-concept-advisory/v1'
f=ROOT/'provider-requests.private.jsonl'
with f.open('a') as out:out.write(json.dumps(v)+'\\n');out.flush();os.fsync(out.fileno())
f.chmod(0o600)
fault=(ROOT/'fault.private').read_text().strip() if (ROOT/'fault.private').exists() else ''
if fault=='timeout':time.sleep(20)
if fault=='slow':time.sleep(1)
r=v['request'];field='users' if r['advisor_kind']=='BUSINESS' else 'constraints'
response={'contract_version':v['contract_version'],'request_digest':v['request_digest'],'briefing_digest':r['briefing_digest'],
'advisor_kind':r['advisor_kind'],'language':r['language'],'answer':'Synthetic model fixture: narrow the initial audience and validate the assumptions.',
'questions':['Who confirms the intended audience?'],'assumptions':['The supplied briefing does not establish operational readiness.'],
'changes':[{'field':field,'before':r['briefing']['fields'][field],'proposed':'Local volunteers' if field=='users' else 'No sensitive recipient data in the first pilot',
'reason':'A bounded pilot reduces untested assumptions.','references':v['context']['evidence_references'][:1]}],'applied':False}
translations={'nl': ['Synthetische modelproef: begin met een beperkte doelgroep en toets de aannames.', 'Wie bevestigt de beoogde doelgroep?', 'De briefing bewijst nog geen operationele gereedheid.', 'Lokale vrijwilligers', 'Geen gevoelige ontvangersgegevens in de eerste proef', 'Een beperkte proef verkleint onbewezen aannames.'], 'de': ['Synthetischer Modelltest: begrenzen Sie die Zielgruppe und prüfen Sie die Annahmen.', 'Wer bestätigt die Zielgruppe?', 'Das Briefing belegt keine Betriebsbereitschaft.', 'Lokale Freiwillige', 'Keine sensiblen Empfängerdaten im ersten Pilotprojekt', 'Ein begrenzter Pilot reduziert ungeprüfte Annahmen.'], 'fr': ['Test de modèle synthétique : limitez le public initial et vérifiez les hypothèses.', 'Qui confirme le public visé ?', 'Le brief ne démontre pas une disponibilité opérationnelle.', 'Bénévoles locaux', 'Aucune donnée sensible des destinataires dans le premier pilote', 'Un pilote limité réduit les hypothèses non vérifiées.'], 'es': ['Prueba de modelo sintético: limite el público inicial y valide las suposiciones.', '¿Quién confirma el público previsto?', 'El briefing no demuestra preparación operativa.', 'Voluntarios locales', 'Sin datos sensibles de destinatarios en el primer piloto', 'Un piloto limitado reduce las suposiciones no verificadas.']}
if r['language'] in translations:
 t=translations[r['language']];response['answer']=t[0];response['questions']=[t[1]];response['assumptions']=[t[2]];response['changes'][0]['proposed']=t[3] if field=='users' else t[4];response['changes'][0]['reason']=t[5]
if fault=='inject':response['changes'][0]['field']='shell';response['tool_calls']=[]
if fault=='foreign':response['changes'][0]['references']=['invented-live-inspection']
Path(a[a.index('--output-last-message')+1]).write_text(json.dumps(response))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':60}}))
'''


def configure(root):
    from forge.runtime.bootstrap import RuntimeBootstrap
    from forge.operator_identity import InstallationOperatorService, MacOSGeneratedUIDIdentityAdapter
    from forge.provider_security import PlanningProviderSecurityService, ProviderAuthenticationMode, CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, CODEX_CLI_CHATGPT_SESSION_TYPE
    from forge.provider_context import ProviderExecutionContextService
    from forge.concept_advisory_grant import ConceptAdvisoryGrant
    from forge.concept_advisory_service import provider_profile
    root=Path(root); root.mkdir(mode=0o700)
    executable=root/'external-provider'; executable.write_text(EXTERNAL.replace('PYTHON',sys.executable).replace('ROOT_LITERAL',repr(str(root)))); executable.chmod(0o700)
    with RuntimeBootstrap(data_root=root/'runtime',forge_version='qualification').open() as db:
        owner=InstallationOperatorService(db,MacOSGeneratedUIDIdentityAdapter().resolve);context=owner.first_bind();instance=db.runtime_identity.runtime_id
        PlanningProviderSecurityService(db,None,owner).configure(configuration_id='synthetic-config',provider_id='concept-fixture',operator_context=context,
           authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
           external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,executable_path=str(executable),adapter_version='codex-cli-chatgpt-session-v1',
           profile='explicit-synthetic-profile',timeout_seconds=2,input_token_bound=40000,context_token_bound=48000,output_token_bound=8000)
    (root/'home').mkdir(mode=0o700);(root/'config').mkdir(mode=0o700)
    ProviderExecutionContextService(root/'runtime').configure(provider_id='concept-fixture',provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
        executable_path=str(executable),provider_home=str(root/'home'),provider_config_home=str(root/'config'),profile='explicit-synthetic-profile')
    grant=ConceptAdvisoryGrant(root/'runtime',instance);grant.initialize();profile=provider_profile(root/'runtime','concept-fixture')
    for name in ('alice','bob'):
        grant.issue(principal_id=name,audience='synthetic-workspace',dossier_ids=['dossier-'+name],conversation_ids=['conversation-'+name,'other-'+name],
          permissions=['READ','ADVISE'],maximum_turns=8,maximum_tokens=384000,maximum_seconds=16,provider_id='concept-fixture',transfer_policy_digest=profile['transfer_policy_digest'],
          expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=root/(name+'.private'))
    (root/'admin.private').write_text('a'*48);(root/'admin.private').chmod(0o600)
    return grant

if __name__ == '__main__':
    grant=configure(Path(sys.argv[1]))
    print(json.dumps({'configured': True, 'provider_evidence': 'MODELED_EXTERNAL_PROVIDER','grant_ids':{r['principal_id']:r['grant_id'] for r in grant._records()}}))
