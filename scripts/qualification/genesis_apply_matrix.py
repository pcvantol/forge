"""Extra qualified-peer HTTP probes; explicit synthetic owner fixtures only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import http.client
import json
from pathlib import Path


def peer(Q, c, label, method='GET', body=None, headers=None, token=None):
    p=c['config'];h={'Authorization':'Bearer '+(token or c['ep_token'].read_text().strip()),
        'EP-Bootstrap-Contract':'1.0','EP-Instance-ID':p['binding']['instance_id'],
        'EP-Host-ID':p['binding']['host_id'],'EP-Consumer-ID':p['binding']['consumer_id'],
        'EP-Principal':p['binding']['principal'],'EP-Audience':'genesis-bootstrap'}
    h.update(headers or {})
    path='/v1/bootstrap/genesis/operations'+('/original-apply' if method=='GET' else '')
    raw=Q.canonical(body) if body is not None else None
    if raw is not None:h['Content-Type']='application/json'
    connection=http.client.HTTPConnection('127.0.0.1',c['ep'].port,timeout=35)
    try:
        connection.request(method,path,body=raw,headers=h);response=connection.getresponse()
        value=response.read(524289)
        if len(value)>524288:raise RuntimeError('finite negative response required')
        result=json.loads(value)
        Q.private(c['output']/(label+'.ep-http.private.json'),dict(status=response.status,response=result))
        return response.status,result
    finally:connection.close()


def prechecks(Q,c):
    """Actual authority/header/body refusals before the sole real admission."""
    ep=c['ep'];baseline=ep.facts();labels=[]
    c['command'](['-m','forge.genesis_apply_cli',*c['data'],'issue','--principal-id',c['setup']['human_principal_id'],
        *c['scope'],'--permission','READ','--token-file',str(c['forge']/'read.private')],c['forge'])
    status,_=Q.retained_call(c['output'],'real-read-grant-cannot-apply',c['port'],c['forge']/'read.private',
        'POST','/v1/genesis-apply/operations',c['body'])
    if status!=403:raise RuntimeError('real READ grant promoted into apply authority')
    for key in ('EP-Instance-ID','EP-Host-ID','EP-Consumer-ID','EP-Principal','EP-Audience'):
        status,_=peer(Q,c,'wrong-'+key,headers={key:'foreign'})
        if status not in (401,403):raise RuntimeError('wrong actual EP binding not denied')
        labels.append(key)
    for key in ('target','actor','bundle','manifest','validator','proposed-identity'):
        value=deepcopy(c['ep_request'])
        if key=='target':value['target_ref']='foreign'
        elif key=='actor':value['effect_plan_binding']['source_actor_id']='foreign'
        else:
            name='engineering/bootstrap-manifest.json' if key=='manifest' else 'engineering/baselines/portable-docs/1.0.0/validate.py' if key=='validator' else '.engineering-platform/repository.json' if key=='proposed-identity' else 'README.md'
            item=value['bundle']['files'][name]
            if key in ('manifest','proposed-identity'):
                document=json.loads(item['utf8'])
                if key=='manifest':document['manifest_digest']='f'*64
                else:document['repository']['id']='foreign-core'
                item['utf8']=Q.canonical(document).decode()
            else:item['utf8']+='\n# changed synthetic negative\n'
            item['sha256']=sha256(item['utf8'].encode()).hexdigest()
        status,_=peer(Q,c,'wrong-original-'+key,'POST',value)
        if status not in (400,403,409,422):raise RuntimeError('changed original EP request accepted')
        labels.append(key)
    # Issue a genuine separate INSPECT_READ bearer; never run an inspection.
    ep.command('preproject_cli','init')
    host=ep.root/'host';(host/'.engineering').mkdir(parents=True,mode=0o700)
    Q.private(host/'.engineering/engineering-platform.local.json',{'workspace':{'workspace_authorization':{
        'allowed_roots':[{'path':str(ep.workspace),'repository_scope':'direct_children'}],
        'allowed_repositories':[],'denied_repositories':[],'symlink_policy':'reject','case_sensitivity':'host'}}})
    binding=ep.root/'inspection-binding.private.json'
    Q.private(binding,dict(source_ref='r57-read-only-source',host_root=str(host),workspace_root=str(ep.workspace),child='r'))
    ep.command('preproject_cli','bind-source','--config',str(binding))
    config=ep.root/'inspection-grant.private.json'
    Q.private(config,dict(grant_id='r57-inspect-only',source_ref='r57-read-only-source',consumer_id='forge-r57',
        principal='synthetic-r57-owner',audience='genesis-bootstrap',paths=['README.md'],content_paths=[],ttl_seconds=3600,max_operations=1))
    old=ep.command('preproject_cli','issue','--config',str(config))
    status,_=peer(Q,c,'real-inspection-grant-cannot-apply','POST',c['ep_request'],token=old['credential'])
    if status!=401:raise RuntimeError('real inspection bearer promoted into Genesis authority')
    if ep.facts()!=baseline:raise RuntimeError('pre-admission negative performed an EP operation')
    return {'actual_read_grant_refused':True,'actual_inspection_grant_refused':True,'binding_refusals':labels,'no_admission':True}


def availability_and_progress(Q,c,operation):
    """Original reads cannot launder unavailable peers or other-purpose bearers."""
    ep=c['ep'];baseline=ep.facts();path='/v1/genesis-apply/operations/original-apply?dossier_id=synthetic-dossier'
    ep.stop()
    status,_=Q.retained_call(c['output'],'unavailable-peer-not-cached-complete',c['port'],c['forge']/'apply.private','GET',path)
    if status!=503:raise RuntimeError('unavailable peer returned a healthy cached result')
    ep.start(fault=False)
    status,value=Q.retained_call(c['output'],'restored-peer-original-read',c['port'],c['forge']/'apply.private','GET',path)
    if status!=200 or value['original_ep_operation']['commit']!=operation['commit']:raise RuntimeError('original peer recovery differs')
    ids=c['documents']['identity'];config=ep.root/'progress-grant.private.json'
    Q.private(config,dict(grant_id='r57-progress-only',consumer_id='forge-r57',workspace_instance_id='synthetic-workspace',
        selections=[dict(project_id=ids['project_id'],authority_repository_id=ids['authority_repository_id'],
            repository_ids=[ids['repository_id']],mission_ids=['unselected-synthetic-scope'],producer_ids=['synthetic-producer'])],
        fields=['identity','progress','result','history'],operation_id='owner-issue-progress-only',ttl_seconds=3600))
    old=ep.command('execution_progress_cli','issue','--config',str(config))
    status,_=peer(Q,c,'real-progress-grant-cannot-apply','POST',c['ep_request'],token=old['credential'])
    if status!=401:raise RuntimeError('real progress bearer promoted into Genesis authority')
    if ep.facts()!=baseline:raise RuntimeError('availability or purpose probe performed an EP effect')
    return {'unavailable503_then_original200':True,'actual_progress_grant_refused':True,'no_extra_effect':True}


def source_change(Q,c,kind):
    """Supersede real synthetic content/effect decisions through owning HTTP."""
    ep=c['ep'];baseline=ep.facts();port=c['port'];forge=c['forge']
    if kind=='R54':
        status,view=Q.C.call(port,forge/'decide.private','GET','/v1/project-proposal-decisions/proposals/'+c['proposal']['plan_id']+'?dossier_id=synthetic-dossier')
        if status!=200:raise RuntimeError('own content source unavailable')
        request=Q.C.request_for(view,'BUSINESS','synthetic-source-changes');request['decision']='REQUEST_CHANGES'
        status,_=Q.C.call(port,forge/'decide.private','POST','/v1/project-proposal-decisions/decisions',request)
    else:
        request={**c['effect_request'],'operation_id':'synthetic-effect-changes','decision':'REQUEST_CHANGES',
            'expected_decision_revision':1,'previous_decision_id':c['decision']['decision_id']}
        status,_=Q.C.call(port,forge/'effect.private','POST','/v1/genesis-bootstrap/decisions',request)
    if status!=200:raise RuntimeError('own synthetic source supersession failed')
    status,_=Q.retained_call(c['output'],'changed-'+kind+'-cannot-apply',port,forge/'apply.private','POST','/v1/genesis-apply/operations',c['body'])
    if status!=409:raise RuntimeError('superseded source still authorized an effect')
    status,view=Q.retained_call(c['output'],'changed-'+kind+'-historical-original',port,forge/'apply.private','GET',
        '/v1/genesis-apply/operations/original-apply?dossier_id=synthetic-dossier')
    if status!=200 or view['effect_decision_currently_applicable'] or view['state']!='COMPLETE':raise RuntimeError('historical original versus current applicability lost')
    if ep.facts()!=baseline:raise RuntimeError('changed content/effect caused a new EP effect')
    return {'changed_source':kind,'new_effect_refused409':True,'historical_complete_currently_inapplicable':True,'no_extra_effect':True}


def before_refusal(Q,c,kind):
    """No real admission for expired/revoked permission or a raced target."""
    import time
    ep=c['ep'];baseline=ep.facts();witness=None
    if kind=='REVOKE':
        ep.command('genesis_cli','revoke','--grant-id','r57-owner-genesis','--operation-id','owner-before-apply-revoke')
    elif kind=='EXPIRE':
        remaining=(datetime.fromisoformat(c['ep_grant']['expires_at'])-datetime.now(UTC)).total_seconds()
        if remaining>35:raise RuntimeError('finite actual expiry fixture required')
        if remaining>0:time.sleep(remaining+.1)
    elif kind=='TARGET_RACE':
        ep.target.mkdir(mode=0o700);witness=ep.target/'race.private';Q.private(witness,b'original synthetic raced target\n')
        identity=[ep.target.stat().st_dev,ep.target.stat().st_ino]
    status,value=Q.retained_call(c['output'],'actual-before-'+kind,c['port'],c['forge']/'apply.private','POST','/v1/genesis-apply/operations',c['body'])
    expected=403 if kind=='EXPIRE' else 424
    if status!=expected:raise RuntimeError('before-admission negative did not refuse at its precise boundary')
    if kind!='EXPIRE' and value.get('error',{}).get('code')!=('EP_GENESIS_HTTP_401' if kind=='REVOKE' else 'EP_GENESIS_HTTP_409'):
        raise RuntimeError('unrelated producer failure cannot prove this authority/target refusal')
    if ep.facts()!=baseline:raise RuntimeError('before-admission refusal created an EP operation/effect')
    if witness and (witness.read_bytes()!=b'original synthetic raced target\n' or [ep.target.stat().st_dev,ep.target.stat().st_ino]!=identity):
        raise RuntimeError('raced target was replaced or changed')
    if kind in ('EXPIRE','REVOKE'):
        ep_status,ep_value=peer(Q,c,'actual-current-owner-'+kind)
        if ep_status!=401 or ep_value!={'error':'BOOTSTRAP_GRANT_INACTIVE'}:raise RuntimeError('actual EP did not independently enforce current authority')
    return {'kind':kind,'forge_status':status,'no_ep_admission_or_effect':True,'raced_target_preserved':witness is not None}


def reservation_refusal(Q,c):
    """Seed one genuine other EP admission, never fabricated SQL or target."""
    import time
    ep=c['ep'];args=ep.args
    if args.crash_boundary!='ACCEPT':raise RuntimeError('reservation fixture requires explicit owning admission barrier')
    seed=deepcopy(c['ep_request']);seed['operation_id']='reservation-seed'
    config=json.loads((ep.root/'grant.private.json').read_bytes())
    config.update(grant_id='r57-other-reservation',issuance_id='owner-other-reservation',target_name='seed',request=seed)
    path=ep.root/'reservation-owner.private.json';Q.private(path,config)
    grant=ep.command('genesis_cli','issue','--config',str(path))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(peer,Q,c,'actual-other-reservation','POST',seed,token=grant['credential'])
        marker=ep.root/'barrier.private.json';deadline=time.monotonic()+30
        while not marker.exists():
            if time.monotonic()>deadline:raise TimeoutError('real other reservation not reached')
            time.sleep(.05)
        value=json.loads(marker.read_bytes())
        if value!={'pid':ep.process.pid,'point':'ACCEPT'}:raise RuntimeError('own seed reservation child differs')
        before=ep.facts()
        rows=before[2]['ep_genesis_operations']
        if len(rows)!=1 or rows[0]['operation_id']!='reservation-seed' or rows[0]['state']!='RESERVED' or json.loads(rows[0]['original_request'])!=seed:
            raise RuntimeError('actual other original reservation not established')
        Q.private(c['output']/'real-reservation-before-crash.private.json',dict(counts=before[0],evidence=before[1],rows=before[2]))
        ep.stop()
        # The physically interrupted seed request is explicitly uncertain.
        try:pending.result(timeout=40)
        except (OSError,http.client.HTTPException):pass
    ep.start(fault=False)
    status,refusal=Q.retained_call(c['output'],'actual-conflicting-reservation-refused',c['port'],c['forge']/'apply.private',
        'POST','/v1/genesis-apply/operations',c['body'])
    if status!=424 or refusal.get('error',{}).get('code')!='EP_GENESIS_HTTP_409':raise RuntimeError('conflicting actual EP reservation not precisely refused')
    after=ep.facts()
    if after!=before or after[0]['ep_genesis_operations']!=1 or any(after[0][t] for t in ('ep_project_registrations','ep_repository_registrations','ep_local_repository_bindings')):
        raise RuntimeError('conflicting reservation caused new admission/effects')
    if ep.target.exists() or (ep.workspace/'seed').exists():raise RuntimeError('reservation fixture performed physical target effects')
    return {'seed':'actual-owner-issued-other-original-admission','conflicting_forge_status':status,
        'seed_admission_only':True,'no_targets_commits_or_attachments':True}


def concurrent_original(Q,c):
    def submit(index):
        body=deepcopy(c['body'])
        if index==2:body['plan_digest']='f'*64
        return Q.retained_call(c['output'],'concurrent-intent-'+str(index),c['port'],c['forge']/'apply.private',
            'POST','/v1/genesis-apply/operations',body)
    with ThreadPoolExecutor(max_workers=3) as pool:values=list(pool.map(submit,range(3)))
    if values[2][0] not in (403,409):raise RuntimeError('concurrent changed intent was accepted')
    if any(status not in (200,409,424,503) for status,value in values[:2]):raise RuntimeError('unexpected concurrent original outcome')
    for status,value in values[:2]:
        if ((status==503 and value.get('error',{}).get('code') not in ('EP_GENESIS_TRANSPORT_UNCERTAIN','EP_GENESIS_DEADLINE_EXCEEDED'))
                or (status==424 and value.get('error',{}).get('code')!='EP_GENESIS_HTTP_404')
                or (status==409 and value.get('error',{}).get('code')!='GENESIS_LATE_RESPONSE_FENCED')):
            raise RuntimeError('unrelated source/storage/authority failure cannot prove concurrency')
    for status,value in values[:2]:
        if status==200:return status,value,{'original_statuses':[v[0] for v in values[:2]],'conflict_status':values[2][0]}
    for status,value in values[:2]:
        if status==503:return status,value,{'original_statuses':[v[0] for v in values[:2]],'conflict_status':values[2][0]}
    raise RuntimeError('no actual original response or transport uncertainty to recover')


def late_publication(Q,c):
    """A real owning EP read completes before Forge's original bearer is revoked."""
    import time
    ep=c['ep'];baseline=ep.facts();args=ep.args;old=getattr(args,'crash_boundary',None)
    ep.stop();args.crash_boundary='READ_THREAD';ep.start()
    marker=ep.root/'barrier.private.json'
    if marker.exists():raise RuntimeError('late response requires an exclusive unused barrier')
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(Q.retained_call,c['output'],'actual-late-publication',c['port'],c['forge']/'apply.private',
                'GET','/v1/genesis-apply/operations/original-apply?dossier_id=synthetic-dossier')
            try:
                deadline=time.monotonic()+15
                while not marker.exists():
                    if time.monotonic()>deadline:raise TimeoutError('real late EP read boundary unavailable')
                    time.sleep(.02)
                value=json.loads(marker.read_bytes())
                if value!={'pid':ep.process.pid,'point':'READ_THREAD'}:raise RuntimeError('own late-response child identity differs')
                c['command'](['-m','forge.genesis_apply_cli',*c['data'],'revoke','--grant-id',c['apply_issue']['grant_id']],c['forge'])
            finally:
                # Release only our exact read barrier, also on a failed revoke.
                import sys
                primary=sys.exc_info()[1]
                try:Q.private(ep.root/'barrier.private.json.release',b'release own finite synthetic barrier\n')
                except BaseException as release:
                    if primary is None:raise
                    primary.add_note('own barrier release failed: '+type(release).__name__)
            status,_=future.result(timeout=35)
        if status!=403:raise RuntimeError('late actual EP response escaped revoked Forge publication')
        if ep.facts()!=baseline:raise RuntimeError('late response probe performed an EP effect')
    finally:
        import sys
        primary=sys.exc_info()[1];errors=[];stopped=False
        try:ep.stop();stopped=True
        except BaseException as error:errors.append(error)
        args.crash_boundary=old
        if stopped:
            try:ep.start(fault=False)
            except BaseException as error:errors.append(error)
        if errors:
            if primary is not None:
                for error in errors:primary.add_note('late-publication cleanup: '+type(error).__name__)
            else:
                for error in errors[1:]:errors[0].add_note('additional cleanup: '+type(error).__name__)
                raise errors[0]
    return {'actual_peer_read_before_owner_revoke':True,'actual_protected_status':403,'no_extra_ep_effect':True}


def concurrent_readbacks(Q,c,operation):
    values=[]
    for index in range(2):
        status,value=Q.retained_call(c['output'],'original-concurrent-readback-'+str(index),c['port'],c['forge']/'apply.private',
            'GET','/v1/genesis-apply/operations/original-apply?dossier_id=synthetic-dossier')
        if (status!=200 or value['state']!='COMPLETE' or value['original_request']!=c['body']
                or value['original_ep_operation']['commit']!=operation['commit']
                or value['original_ep_operation']['tree']!=operation['tree'] or value['explicit_attempts']!=1):
            raise RuntimeError('concurrent original caller did not recover the same single committed operation')
        values.append({'status':status,'operation_id':value['operation_id'],'commit':operation['commit'],'explicit_attempts':1})
    return values


def retain_owned(Q,root,ep,output):
    """Private primary bytes after own processes stop, before exclusive cleanup.

    Raw bearer/config containers and credentials directories are excluded.
    Nothing is extracted or followed through an archived symlink.
    """
    import os
    import tarfile
    selected=[('ep-target',ep.target),('ep-native-evidence',ep.data/'g/evidence'),
        ('forge-onboarding',root/'f/runtime/onboarding')]
    for base,path in (('ep-central',ep.data/'epdata.sqlite'),('forge-central',root/'f/runtime/forge.db')):
        for suffix in ('','-wal','-shm'):
            value=Path(str(path)+suffix)
            if value.exists():selected.append((base+suffix,value))
    archive=output/'owned-primary-evidence.private.tar'
    import stat
    def add_owned(saved,fd,archive_name):
        # Every component is opened relative to a pinned own directory. No
        # symlink, special file or externally hardlinked payload is admissible.
        try:
            before=os.fstat(fd)
            if before.st_uid!=os.getuid():raise RuntimeError('archive ownership differs')
            item=tarfile.TarInfo(archive_name);item.mode=stat.S_IMODE(before.st_mode)
            item.uid=before.st_uid;item.gid=before.st_gid;item.mtime=before.st_mtime
            if stat.S_ISDIR(before.st_mode):
                item.type=tarfile.DIRTYPE;saved.addfile(item)
                for child in sorted(os.listdir(fd)):
                    childfd=os.open(child,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
                    add_owned(saved,childfd,archive_name+'/'+child)
            elif stat.S_ISREG(before.st_mode) and before.st_nlink==1:
                item.size=before.st_size
                with os.fdopen(os.dup(fd),'rb') as payload:saved.addfile(item,payload)
                after=os.fstat(fd)
                if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                    raise RuntimeError('archive payload changed during capture')
            else:raise RuntimeError('archive symlink/special/hardlink refused')
        finally:os.close(fd)
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        marker=__import__('json').loads((root/'.r57-owner.json').read_bytes())
        info=os.fstat(rootfd)
        if marker['uid']!=os.getuid() or marker['identity']!=[info.st_dev,info.st_ino]:raise RuntimeError('archive root identity differs')
        with archive.open('xb') as stream:
            os.chmod(archive,0o600)
            with tarfile.open(fileobj=stream,mode='w',dereference=False) as saved:
                for name,path in selected:
                    parts=path.relative_to(root).parts
                    parent=os.dup(rootfd)
                    try:
                        for part in parts[:-1]:
                            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                            os.close(parent);parent=child
                        selectedfd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
                    except FileNotFoundError:continue  # Only absent optional selection, never recursive payload loss.
                    finally:os.close(parent)
                    add_owned(saved,selectedfd,name)
            stream.flush();os.fsync(stream.fileno())
    finally:os.close(rootfd)
    with tarfile.open(archive,'r') as saved:
        members=saved.getmembers()
        if any(p.name.startswith('/') or '..' in Path(p.name).parts for p in members):raise RuntimeError('own archive member boundary differs')
        # Consume every retained regular payload to reject truncated tar data.
        for member in members:
            if member.isfile():
                with saved.extractfile(member) as payload:
                    while payload.read(65536):pass
    result={'archive':archive.name,'sha256':sha256(archive.read_bytes()).hexdigest(),'members':len(members),
        'private':True,'raw_bearers_and_config_containers_excluded':True,'owned_processes_stopped_before_capture':True}
    Q.private(output/'owned-primary-evidence.private.json',result)
    return result
