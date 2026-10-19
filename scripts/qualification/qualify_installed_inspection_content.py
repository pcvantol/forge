"""R59 real installed HTTP over the original owning R55 qualification fixture."""
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
from datetime import UTC, datetime, timedelta
import argparse
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import http.client
import json
import re
import subprocess
import shutil
import time

spec = spec_from_file_location('owning_r55',Path(__file__).with_name('qualify_installed_inspection_adoption.py'))
R55 = module_from_spec(spec)
spec.loader.exec_module(R55)
BASE = '/v1/inspection-adoption-decisions'
CONTRACT = 'forge-inspection-adoption-content-decision/v1'
PROFILE = 'INSPECTION_ADOPTION_CONTENT_ONLY/1.0'


def decision(view, role, operation):
    return {'contract_version':CONTRACT,'profile_id':PROFILE,'instance_id':view['instance_id'],
            'dossier_id':view['dossier_id'],'plan_id':view['plan_id'],'operation_id':operation,
            'subject_digest':view['subject']['subject_digest'],'role':role,'decision':'APPROVE_CONTENT',
            'reason':'SYNTHETIC_TEST_NOT_PETER_APPROVAL: exact historical document review only.',
            'expected_decision_revision':view['decision_revision'],
            'previous_decision_id':view['history'][-1]['decision_id'] if view['history'] else None,
            'acknowledged_review_digest':view['review_digest']}


def lose_complete_success(port, headers, body):
    """External loss relay consumes the full success, then drops the client reply."""
    audit = []
    class LossRelay(BaseHTTPRequestHandler):
        def do_POST(self):
            connection = http.client.HTTPConnection('127.0.0.1',port,timeout=15)
            try:
                size = int(self.headers['Content-Length'])
                if self.path != BASE+'/decisions' or not 0 < size <= 65536 or audit:
                    raise ValueError('one exact finite POST required')
                request = self.rfile.read(size)
                if len(request) != size:
                    raise ValueError('complete decision request required')
                connection.request('POST',self.path,body=request,headers={**headers,'Content-Type':'application/json'})
                response = connection.getresponse()
                expected = int(response.getheader('Content-Length'))
                raw = response.read(1048577)
                if response.status != 200 or len(raw) != expected or not 0 < expected <= 1048576:
                    raise ValueError('full original successful response required')
                value = json.loads(raw)
                audit.append({'success_status':response.status,'full_content_length':expected,'received_bytes':len(raw),
                              'response_sha256':sha256(raw).hexdigest(),'decision_id':value['original_decision']['decision_id'],
                              'operation_id':value['original_decision']['request']['operation_id'],
                              'loss':'FULL_SUCCESS_RECEIVED_BY_EXTERNAL_RELAY_DROPPED_BEFORE_CONSUMER'})
                # No response headers/body reach the consumer; it must recover original intent only.
                self.close_connection = True
            except BaseException as error:
                audit.append({'error_type':type(error).__name__})
                self.close_connection = True
            finally:
                connection.close()
        def log_message(self,*_):pass
    relay = ThreadingHTTPServer(('127.0.0.1',0),LossRelay)
    thread = Thread(target=relay.serve_forever,daemon=True);thread.start()
    client = http.client.HTTPConnection('127.0.0.1',relay.server_port,timeout=20)
    lost = False
    try:
        client.request('POST',BASE+'/decisions',body=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:client.getresponse()
        except http.client.RemoteDisconnected:lost = True
    finally:
        client.close();relay.shutdown();thread.join(3);relay.server_close()
    assert lost and not thread.is_alive() and len(audit) == 1 and audit[0].get('success_status') == 200,audit
    return audit[0]


def retain_fault(output, label, outcome, *, binding, detector, original, mutation, restored=False):
    """Only verified-safe detector output is public; private source/credentials never are."""
    if outcome.stdout != b'' or len(outcome.stderr) > 4096:
        raise RuntimeError('detector output not safe for public retention')
    stderr = outcome.stderr.decode('ascii')
    allowed = (r'Traceback \(most recent call last\):\n  File "<string>", line 1, in <module>\n'
               + '(?:    '+re.escape(detector)+r'\n[ ~^]+\n)?'
               + r'AssertionError: revoked-role-approval-detector\n')
    if label == 'RED':
        if outcome.returncode == 0 or re.fullmatch(allowed,stderr) is None:
            raise RuntimeError('original RED detector failure not safe or expected')
    elif label != 'GREEN' or outcome.returncode != 0 or stderr or not restored:
        raise RuntimeError('restored GREEN detector outcome required')
    value = {'scope':'R59_INSTALLED_ROLE_APPLICABILITY_FAULT','label':label,'binding':binding,
             'detector_sha256':sha256(detector.encode()).hexdigest(),'original_product_file_sha256':sha256(original).hexdigest(),
             'faulty_product_file_sha256':sha256(mutation).hexdigest(),'original_returncode':outcome.returncode,
             'original_stdout_text':'','original_stderr_text':stderr,
             'original_stdout_sha256':sha256(outcome.stdout).hexdigest(),'original_stderr_sha256':sha256(outcome.stderr).hexdigest(),
             'expected_healthy_state':'DECISION_NEEDED','original_product_bytes_restored':restored}
    path = output/('r59-restored-fault-'+label+'.public.json')
    if path.exists():
        raise RuntimeError('preserve original detector receipt')
    R55.private(path,value)
    return {'file':path.name,'sha256':sha256(path.read_bytes()).hexdigest()}


def probe(phase,args,root,forge_root,setup,proposal,server,command,receipt,output):
    def cli(action,*arguments):
        return command(args.python,'forge.inspection_content_cli','--data-root',forge_root/'runtime',action,*arguments)
    def headers(token):
        return {'Authorization':'Bearer '+(root/(token+'.private')).read_text().strip(),
                'X-Forge-Inspection-Content-Audience':'synthetic-workspace'}
    def call(port,method,target,token,body=None,lost=False):
        response = R55.request(port,method,target,headers(token),body,lost=lost)
        if not lost:
            from jsonschema import Draft202012Validator
            schema = json.loads((R55.SOURCE/'forge/api/inspection-adoption-decisions-v1.json').read_text())
            Draft202012Validator(schema).validate(response[2])
            if response[0] == 200 and body is not None:
                Draft202012Validator(schema).validate(body)
        return response
    target = BASE+'/proposals/'+proposal['plan_id']+'?dossier_id=synthetic-dossier'
    original = BASE+'/intents/r59-business-original?dossier_id=synthetic-dossier'
    own = forge_root/'runtime/onboarding/inspection-content-decisions/store.json'
    if phase == 'decide':
        source_reader = command(args.python,'forge.ep_inspection_cli','--data-root',forge_root/'runtime','issue',
            '--principal-id','synthetic-service','--audience','synthetic-workspace','--dossier-id','synthetic-dossier',
            '--permission','READ','--pairing-id','selected-original','--maximum-records','4',
            '--expires-at',(datetime.now(UTC)+timedelta(minutes=10)).isoformat(),'--token-file',root/'r59-source-read.private')
        R55.private(output/'r59-source-read-grant.private.json',source_reader)
        cli('init')
        grants = {}
        for role in ('BUSINESS','ARCHITECTURE'):
            grants[role] = cli('issue','--principal-id',setup['human_principal_id'],'--audience','synthetic-workspace',
                '--dossier-id','synthetic-dossier','--plan-id',proposal['plan_id'],'--source-token-file',root/'r59-source-read.private',
                '--permission','READ','--permission','DECIDE','--role',role,
                '--expires-at',(datetime.now(UTC)+timedelta(minutes=5)).isoformat(),'--token-file',root/(role.lower()+'.private'))
        assert grants['BUSINESS']['grant_id'] != grants['ARCHITECTURE']['grant_id']
        receipt['content_decision_human_binding'] = 'ACTUAL_CANONICAL_SOLO_OPERATOR_TWO_SEPARATE_ROLE_GRANTS_NOT_TWO_INVENTED_PEOPLE'
        receipt['content_decision_approval_qualification'] = 'SYNTHETIC_TEST_NOT_PETER_APPROVAL'
        R55.private(output/'r59-grants.private.json',grants)
        with server() as port:
            code,_,view = call(port,'GET',target,'business');assert code == 200,(code,view)
            assert not view['blockers'] and view['review']['source_freshness'] == 'AS_OF_OBSERVATION_NOT_CONTINUOUS'
            entries = {e['artifact_path']:e for e in view['review']['documents']}
            assert entries['docs/product/VISION.md']['operation'] == 'LINK_EXISTING'
            assert 'content' in entries['docs/product/VISION.md']['mapping_source']
            assert entries['docs/architecture/ARCHITECTURE.md']['operation'] == 'PROPOSE_ADDITION'
            assert entries['docs/roadmap/ROADMAP.md']['operation'] == 'INSUFFICIENT_INFORMATION'
            business = decision(view,'BUSINESS','r59-business-original')
            # Send once, deliberately lose response; recover only the original GET.
            loss = lose_complete_success(port,headers('business'),business)
            R55.private(output/'r59-complete-success-loss.private.json',loss)
            deadline = time.monotonic()+10
            while True:
                code,_,partial = call(port,'GET',original,'business')
                if code == 200 and partial['intent_state'] == 'COMMITTED':
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('original R59 intent recovery deadline')
                assert code in (200,403,404),(code,partial)
                time.sleep(.05)
            assert partial['state'] == 'DECISION_NEEDED' and len(partial['history']) == 1
            assert partial['original_decision']['decision_id'] == loss['decision_id']
            receipt['content_decision_lost_success'] = loss
            architecture = decision(partial,'ARCHITECTURE','r59-architecture-original')
            code,_,full = call(port,'POST',BASE+'/decisions','architecture',architecture)
            assert code == 200 and full['state'] == 'CONTENT_APPROVED_ONLY',(code,full)
            assert not full['effects_authorized'] and len(full['history']) == 2
            code,_,direct = call(port,'GET',BASE+'/decisions/'+partial['original_decision']['decision_id']+'?dossier_id=synthetic-dossier','architecture')
            assert code == 200 and direct['original_decision'] == partial['original_decision']

            for token in ('forge-token',):
                assert call(port,'POST',BASE+'/decisions',token,{**business,'operation_id':'r59-denied-purpose'})[0] in (401,403)
            assert call(port,'POST',BASE+'/decisions','business',{**business,'operation_id':'r59-wrong-subject','subject_digest':'f'*64})[0] == 409
            assert call(port,'POST',BASE+'/decisions','business',{**business,'operation_id':'r59-stale'})[0] == 409
            for token,expected in [('business',partial),('architecture',full)]:
                R55.private(output/('r59-'+token+'-decision.private.json'),expected)
            parity = cli('read','--plan-id',proposal['plan_id'],'--dossier-id','synthetic-dossier','--token-file',root/'architecture.private','--audience','synthetic-workspace')
            assert parity['history'] == full['history'] and parity['state'] == full['state']
        receipt['cases'].append('r59-two-finite-role-grants-exact-dutch-source-lost-success-original-get-no-second-post-cli-parity')
    else:
        # Owning R55 runner has now separately restarted EP; a new Forge OS process reads the same history.
        retained = json.loads((output/'r59-business-decision.private.json').read_text())
        with server() as port:
            code,_,recovered = call(port,'GET',original,'business')
            assert code == 200 and recovered['original_decision'] == retained['original_decision'] and len(recovered['history']) == 2
            for path in (own,own.parent/'initialized.json'):
                saved = path.read_bytes()
                try:
                    path.unlink()
                    assert call(port,'GET',original,'business')[0] != 200
                    R55.private(path,b'corrupt')
                    assert call(port,'GET',original,'business')[0] != 200
                finally:R55.private(path,saved)
            grants = json.loads((output/'r59-grants.private.json').read_text())
            cli('revoke','--grant-id',grants['BUSINESS']['grant_id'])
            assert call(port,'GET',original,'business')[0] != 200
            code,_,current = call(port,'GET',target,'architecture')
            assert code == 200 and current['state'] == 'DECISION_NEEDED' and not current['role_status']['BUSINESS']['currently_applicable']
            assert len(current['history']) == 2
        installed_service = Path(subprocess.check_output([str(args.python),'-I','-c',
            'import forge.inspection_content_service;print(forge.inspection_content_service.__file__)'],cwd=root).decode().strip())
        saved_service = installed_service.read_bytes()
        guard = b'len(current) == len(ROLES)'
        assert saved_service.count(guard) == 1
        detector = "import http.client,json,sys;c=http.client.HTTPConnection('127.0.0.1',int(sys.argv[1]),timeout=15);c.request('GET',sys.argv[2],headers=json.load(sys.stdin));r=c.getresponse();v=json.loads(r.read());assert r.status==200 and v['state']=='DECISION_NEEDED', 'revoked-role-approval-detector'"
        def detect(port):
            return subprocess.run([str(args.python),'-I','-c',detector,str(port),target],input=json.dumps(headers('architecture')).encode(),capture_output=True,cwd=root,timeout=20)
        faulty_service = saved_service.replace(guard,b'len(current) >= 1')
        binding = {k:receipt[k] for k in ('source_revision','source_tree','wheel_sha256','version','operator_identity')}
        try:
            installed_service.write_bytes(faulty_service)
            shutil.rmtree(installed_service.parent/'__pycache__',ignore_errors=True)
            with server() as port:
                red = detect(port)
                R55.private(output/'r59-restored-fault-RED.stdout.private',red.stdout)
                R55.private(output/'r59-restored-fault-RED.stderr.private',red.stderr)
                assert red.returncode != 0 and b'revoked-role-approval-detector' in red.stderr
                red_evidence = retain_fault(output,'RED',red,binding=binding,detector=detector,
                    original=saved_service,mutation=faulty_service)
        finally:
            installed_service.write_bytes(saved_service)
            shutil.rmtree(installed_service.parent/'__pycache__',ignore_errors=True)
            assert installed_service.read_bytes() == saved_service
        with server() as port:
            green = detect(port)
            R55.private(output/'r59-restored-fault-GREEN.stdout.private',green.stdout)
            R55.private(output/'r59-restored-fault-GREEN.stderr.private',green.stderr)
            assert green.returncode == 0
            green_evidence = retain_fault(output,'GREEN',green,binding=binding,detector=detector,
                original=saved_service,mutation=faulty_service,restored=installed_service.read_bytes() == saved_service)
        receipt['content_fault_evidence'] = {'red':red_evidence,'green':green_evidence}
        receipt['cases'].append('r59-restored-real-installed-role-applicability-defect-identical-detector-red-green-original-bytes-restored')
        receipt['cases'].append('r59-separate-forge-ep-restarts-original-history-corrupt-lost-store-denial-revoked-role-no-current-approval')
        with server() as port:
            cli('issue','--principal-id','synthetic-r59-short-reader','--audience','synthetic-workspace',
                '--dossier-id','synthetic-dossier','--plan-id',proposal['plan_id'],'--source-token-file',root/'r59-source-read.private',
                '--permission','READ','--expires-at',(datetime.now(UTC)+timedelta(seconds=10)).isoformat(),'--token-file',root/'r59-short.private')
            assert call(port,'GET',target,'r59-short')[0] == 200
            time.sleep(10.05)
            assert call(port,'GET',target,'r59-short')[0] in (401,403)
            source_reader = json.loads((output/'r59-source-read-grant.private.json').read_text())
            command(args.python,'forge.ep_inspection_cli','--data-root',forge_root/'runtime','revoke','--grant-id',source_reader['grant_id'])
            assert call(port,'GET',target,'architecture')[0] in (401,403)
        receipt['cases'].append('r59-actual-finite-read-expiry-and-owning-source-grant-revoke-deny-retained-private-bytes')
        receipt['content_decision_result'] = 'PASS'
        receipt['content_decisions'] = 2
        receipt['content_decision_scope'] = PROFILE


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for key in ('python','wheel','ep-python','ep-wheel','ep-native-launcher','output-dir'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--source-revision',required=True)
    parser.add_argument('--modeled-os-identity',action='store_true')
    R55.run(parser.parse_args(),content_probe=probe)
