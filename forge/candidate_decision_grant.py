"""Owner-issued Candidate read/decision scopes bound to the real canonical signer."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
import argparse, json, secrets
from .candidate_decision_contract import CONTRACT
from .advisory_candidate_contract import hash_reference
from .advisory_grant import project_scope
from .approved_worklist import identifier, timestamp
from .governance import GovernanceRole, resolve_governance_profile
from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
from .workspace_review_grant import _locked, _private_bytes, _write_private, _new_token

PERMISSIONS = ('READ', 'BUSINESS', 'ARCHITECTURE')
ROLES = {'BUSINESS': GovernanceRole.BUSINESS_OWNER, 'ARCHITECTURE': GovernanceRole.PLATFORM_ARCHITECT}

def signer(root, instance_id, profile_id, permissions, principal_id=None):
    """A token cannot assign a remote person to a local abstract profile role."""
    profile = resolve_governance_profile(profile_id)
    with InstalledDynamicMissionRuntime.open_for_governance_read(str(root)) as runtime:
        if runtime.database.runtime_identity.runtime_id != instance_id:
            raise PermissionError('foreign decision instance')
        context = runtime.repository.operators.context()
        fingerprint = sha256(context.generated_uid.encode()).hexdigest()[:16]
        for permission in permissions:
            if permission == 'READ':
                continue
            if principal_id != fingerprint or profile.role_assignments.get(ROLES[permission]) != ('primary_operator',):
                raise PermissionError('principal does not bind the existing assigned operator role')
            row = runtime.database._connection.execute('SELECT 1 FROM governance_authority WHERE installation_id=? AND operator_id=? AND capability=?', (context.installation_id, fingerprint, permission+'_APPROVAL')).fetchone()
            if row is None:
                raise PermissionError('current governance capability unavailable')
        return {'operator_id': fingerprint, 'operator_binding_version': context.binding_version, 'installation_id': context.installation_id}

@dataclass(frozen=True)
class DecisionPrincipal:
    principal_id: str
    instance_id: str
    project_id: str
    repository_id: str
    grant_id: str
    profile_id: str
    permissions: tuple
    candidates: tuple
    maximum_decisions: int
    operator_id: str
    operator_binding_version: int
    installation_id: str
    @property
    def reference(self):
        return self.instance_id+':'+self.principal_id

class CandidateDecisionGrant:
    def __init__(self, root, instance_id):
        self.root=Path(root); self.instance_id=identifier(instance_id)
        self.path=self.root/'credentials'/'candidate-decisions'/'grants.json'
    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():
            return []
        value=json.loads(_private_bytes(self.path))
        if not isinstance(value,dict) or set(value)!={'contract_version','instance_id','records'} or value['contract_version']!=CONTRACT or value['instance_id']!=self.instance_id or not isinstance(value['records'],list) or len(value['records'])>64:
            raise ValueError('invalid decision grant store')
        seen=set()
        for r in value['records']:
            if not isinstance(r,dict) or set(r)!=set(DecisionPrincipal.__dataclass_fields__)|{'token_digest','expires_at','state'}:
                raise ValueError('invalid decision grant')
            for key in ('principal_id','instance_id','project_id','repository_id','grant_id','operator_id','installation_id'):
                identifier(r[key])
            self._bounds(r['permissions'],r['candidates'],r['maximum_decisions'])
            timestamp(r['expires_at']); resolve_governance_profile(r['profile_id'])
            if r['instance_id']!=self.instance_id or r['state'] not in ('ACTIVE','REVOKED') or r['grant_id'] in seen or type(r['operator_binding_version']) is not int or r['operator_binding_version']<1:
                raise ValueError('invalid decision grant binding')
            h=r['token_digest']
            if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):
                raise ValueError('invalid decision credential digest')
            seen.add(r['grant_id'])
        return value['records']
    @staticmethod
    def _bounds(permissions,candidates,maximum):
        if not isinstance(permissions,(list,tuple)) or 'READ' not in permissions or len(set(permissions))!=len(permissions) or any(p not in PERMISSIONS for p in permissions):
            raise ValueError('explicit decision permissions required')
        if not isinstance(candidates,(list,tuple)) or not 1<=len(candidates)<=16 or len({c['candidate_id'] for c in candidates})!=len(candidates):
            raise ValueError('bounded exact Candidate set required')
        for c in candidates:
            if not isinstance(c,dict) or set(c)!={'candidate_id','subject_revision'}:
                raise ValueError('exact Candidate revision required')
            identifier(c['candidate_id']); hash_reference(c['subject_revision'])
        if type(maximum) is not int or not 1<=maximum<=8:
            raise ValueError('bounded decision allowance required')
    def _save(self,records):
        raw=json.dumps({'contract_version':CONTRACT,'instance_id':self.instance_id,'records':records},sort_keys=True).encode()
        if len(raw)>65536:
            raise ValueError('decision grant capacity exhausted')
        _write_private(self.path,raw)
    def issue(self,*,principal_id,project_id,repository_id,profile_id,permissions,candidates,maximum_decisions,expires_at,token_path):
        identifier(principal_id); self._bounds(permissions,candidates,maximum_decisions)
        if not datetime.now(UTC)<timestamp(expires_at)<=datetime.now(UTC)+timedelta(days=30):
            raise ValueError('finite decision grant required')
        token_path=Path(token_path)
        if token_path.resolve()==self.path.resolve():
            raise ValueError('token/store collision')
        with _locked(self.path):
            binding=signer(self.root,self.instance_id,profile_id,permissions,principal_id)
            scope=project_scope(self.root,self.instance_id)
            if (scope['project_id'],scope['repository_id'])!=(project_id,repository_id):
                raise PermissionError('foreign decision project')
            # Existing canonical registration is the admitted project-bound population.
            from .candidate_decision_service import CandidateDecisionService
            for c in candidates:
                CandidateDecisionService(self.root,self).admitted_candidate(c['candidate_id'],scope,c['subject_revision'])
            records=self._records(True)
            if len(records)>=64:
                raise ValueError('decision grant capacity exhausted')
            token=secrets.token_urlsafe(48)
            r={**scope,**binding,'principal_id':principal_id,'grant_id':'decision-'+secrets.token_hex(16),'profile_id':profile_id,'permissions':sorted(permissions),'candidates':list(candidates),'maximum_decisions':maximum_decisions,'expires_at':expires_at,'state':'ACTIVE','token_digest':sha256(token.encode()).hexdigest()}
            _new_token(token_path,token)
            try:
                self._save([*records,r])
            except Exception:
                token_path.unlink(missing_ok=True)
                raise
            return {k:v for k,v in r.items() if k!='token_digest'}
    def revoke(self,grant_id):
        identifier(grant_id)
        with _locked(self.path):
            signer(self.root,self.instance_id,'solo',('READ',))
            records=self._records(); r=next((r for r in records if r['grant_id']==grant_id),None)
            if r is None:
                raise ValueError('unknown decision grant')
            r['state']='REVOKED'; self._save(records)
            return {'grant_id':grant_id,'state':'REVOKED'}
    def authenticate(self,authorization):
        if not isinstance(authorization,str) or not authorization.startswith('Bearer '):
            return None
        token=authorization[7:]
        if not token or len(token)>256 or any(ord(c)<33 or ord(c)>126 for c in token):
            return None
        try:
            matching=[r for r in self._records() if secrets.compare_digest(r['token_digest'],sha256(token.encode()).hexdigest())]
            r=matching[0] if len(matching)==1 else None
            if r is None or r['state']!='ACTIVE' or timestamp(r['expires_at'])<=datetime.now(UTC):
                return None
            return DecisionPrincipal(**{k:(tuple(r[k]) if k in ('permissions','candidates') else r[k]) for k in DecisionPrincipal.__dataclass_fields__})
        except (OSError,ValueError,KeyError,TypeError):
            return None
    def authorize(self,authorization,candidate_id=None,permission='READ'):
        p=self.authenticate(authorization)
        if p is None or permission not in p.permissions:
            raise PermissionError('decision capability unavailable')
        binding=signer(self.root,self.instance_id,p.profile_id,(permission,),p.principal_id)
        if any(binding[k]!=getattr(p,k) for k in binding) or project_scope(self.root,self.instance_id)!={k:getattr(p,k) for k in ('instance_id','project_id','repository_id')}:
            raise PermissionError('current decision actor/project binding changed')
        if candidate_id is not None and candidate_id not in [c['candidate_id'] for c in p.candidates]:
            raise PermissionError('foreign Candidate scope')
        return p

def main(argv=None):
    parser=argparse.ArgumentParser(prog='forge-candidate-decision-grant'); parser.add_argument('--data-root',required=True)
    sub=parser.add_subparsers(dest='action',required=True); issue=sub.add_parser('issue'); revoke=sub.add_parser('revoke'); revoke.add_argument('--grant-id',required=True)
    sub.add_parser('identity'); sub.add_parser('inspect').add_argument('--candidate-id',required=True)
    for key in ('principal-id','project-id','repository-id','profile-id','expires-at','token-file'):
        issue.add_argument('--'+key,required=True)
    issue.add_argument('--permission',action='append',required=True); issue.add_argument('--candidate',action='append',required=True,help='candidate_id=sha256:revision'); issue.add_argument('--maximum-decisions',type=int,required=True)
    a=parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        i=existing_instance(a.data_root);g=CandidateDecisionGrant(i.data_root,i.instance_id)
        if a.action in ('identity','inspect'):
            binding=signer(g.root,i.instance_id,'solo',('READ',));out={'contract_version':CONTRACT,**binding,'read_only':True}
            if a.action=='inspect':
                from .candidate_decision_service import CandidateDecisionService
                from .models.criterion_observation import canonical_digest
                scope=project_scope(g.root,i.instance_id);candidate,_,_,receipt=CandidateDecisionService(g.root,g).admitted_candidate(a.candidate_id,scope)
                out.update(scope=scope,candidate=candidate.to_dict(),subject_revision=canonical_digest(candidate.to_dict()),source_registration_subject_revision=receipt['candidate_digest'])
        else:
            out=g.revoke(a.grant_id) if a.action=='revoke' else g.issue(principal_id=a.principal_id,project_id=a.project_id,repository_id=a.repository_id,profile_id=a.profile_id,permissions=a.permission,candidates=[dict(zip(('candidate_id','subject_revision'),c.split('=',1))) for c in a.candidate],maximum_decisions=a.maximum_decisions,expires_at=a.expires_at,token_path=a.token_file)
        print(json.dumps(out,sort_keys=True));return 0
    except (OSError,ValueError,RuntimeError,PermissionError,KeyError):
        print(json.dumps({'contract_version':CONTRACT,'error':{'code':'DECISION_GRANT_UNAVAILABLE'}}));return 1

if __name__=='__main__':
    raise SystemExit(main())
