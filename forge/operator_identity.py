"""Trusted installation/operator binding; request strings are not authority."""
from dataclasses import dataclass
import hashlib,json
import os,pwd,subprocess,uuid
from .runtime.database import _timestamp
@dataclass(frozen=True)
class NamedOperatorIdentity: generated_uid:str; uid:int
@dataclass(frozen=True)
class OperatorContext: installation_id:str; generated_uid:str; binding_version:int
class InstallationOperatorService:
 def __init__(self, db, resolver): self.db,self.resolver=db,resolver
 def installation_id(self):
  value=self.db.metadata.get('installation_id')
  if value:return value
  value=str(uuid.uuid4())
  with self.db._connection:self.db._set_metadata({'installation_id':value})
  return value
 def first_bind(self):
  identity=self.resolver(); iid=self.installation_id()
  if not isinstance(identity,NamedOperatorIdentity) or not identity.generated_uid: raise PermissionError('trusted identity required')
  occurred_at=_timestamp()
  with self.db._connection:
   if self.db._connection.execute('SELECT 1 FROM installation_operator_binding WHERE installation_id=?',(iid,)).fetchone():raise PermissionError('already bound')
   self.db._connection.execute('INSERT INTO installation_operator_binding VALUES (?,?,?,?,?,?)',(iid,identity.generated_uid,identity.uid,1,'ACTIVE',occurred_at))
   self._audit(iid,identity,'FIRST_BIND',occurred_at,'ALLOW')
  context=self.context()
  self._pending_governance_bootstrap=(context,occurred_at)
  try:self._bootstrap_governance_after_first_bind()
  finally:del self._pending_governance_bootstrap
  return context
 def context(self):
  identity=self.resolver(); iid=self.installation_id(); row=self.db._connection.execute('SELECT * FROM installation_operator_binding WHERE installation_id=?',(iid,)).fetchone()
  if not row or row['status']!='ACTIVE' or (row['generated_uid'],row['uid'])!=(identity.generated_uid,identity.uid):raise PermissionError('binding denied')
  return OperatorContext(iid,identity.generated_uid,row['version'])
 def authorize(self, context):
  try:return isinstance(context,OperatorContext) and context==self.context()
  except PermissionError:return False
 def _governance_operator_id(self, context): return hashlib.sha256(context.generated_uid.encode()).hexdigest()[:16]
 def _governance_state(self, context):
  operator=self._governance_operator_id(context)
  rows=self.db._connection.execute('SELECT capability FROM governance_authority WHERE installation_id=? AND operator_id=? ORDER BY capability',(context.installation_id,operator)).fetchall()
  return tuple(row['capability'] for row in rows)
 def _persist_governance_capabilities(self, context, kind, provenance):
  if not self.authorize(context): raise PermissionError('trusted bound operator required')
  expected=('ARCHITECTURE_APPROVAL','BUSINESS_APPROVAL','SECURITY_APPROVAL'); state=self._governance_state(context)
  if state:
   if state!=expected: raise PermissionError('conflicting governance capability state')
   return
  operator=self._governance_operator_id(context); now=_timestamp()
  for capability in expected:
   document={**provenance,'installation_id':context.installation_id,'operator_id':operator,'capability':capability,'kind':kind}
   digest='sha256:'+hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest()
   self.db._insert_governance_grant(digest,context.installation_id,operator,capability,json.dumps(document,sort_keys=True,separators=(',',':')),digest,now)
   self.db._insert_governance_authority(context.installation_id,operator,capability,now)
 def _bootstrap_governance_after_first_bind(self):
  """Private G001 first-bind continuation; no caller-supplied identity values."""
  try:context,occurred_at=self._pending_governance_bootstrap
  except AttributeError:raise PermissionError('governance bootstrap is only available during first bind') from None
  self._persist_governance_capabilities(context,'LOCAL_INSTALLATION_BOOTSTRAP_V1',{'first_bind_at':occurred_at,'binding_version':context.binding_version})
 def adopt_governance_capabilities(self, context):
  """One-time adoption for a pre-governance, already-bound G001 installation."""
  if not self.authorize(context): raise PermissionError('trusted bound operator required')
  row=self.db._connection.execute('SELECT created_at,version,status FROM installation_operator_binding WHERE installation_id=?',(context.installation_id,)).fetchone()
  if not row or row['status']!='ACTIVE': raise PermissionError('active G001 binding required')
  self._persist_governance_capabilities(context,'EXISTING_G001_GOVERNANCE_ADOPTION_V1',{'prior_binding_created_at':row['created_at'],'prior_binding_version':row['version'],'adopted_at':_timestamp()})
 def revoke(self, context):
  if not self.authorize(context):raise PermissionError('denied')
  with self.db._connection:
   self.db._connection.execute("UPDATE installation_operator_binding SET status='REVOKED',version=version+1 WHERE installation_id=?",(context.installation_id,))
   self._audit(context.installation_id,NamedOperatorIdentity(context.generated_uid,0),'REVOKE',_timestamp(),'ALLOW')
 def _audit(self, installation_id, identity, operation, occurred_at, result):
  fingerprint=hashlib.sha256(identity.generated_uid.encode()).hexdigest()[:16]
  audit_id=f'{installation_id}:{operation}:{uuid.uuid4()}'
  self.db._connection.execute('INSERT INTO installation_operator_audit VALUES (?,?,?,?,?,?)',(audit_id,installation_id,fingerprint,operation,occurred_at,result))

class MacOSGeneratedUIDIdentityAdapter:
 executable='/usr/bin/dscl'
 def __init__(self, runner=subprocess.run): self.runner=runner
 def resolve(self):
  uid=os.getuid(); name=pwd.getpwuid(uid).pw_name
  result=self.runner([self.executable,'.','-read',f'/Users/{name}','GeneratedUID'],capture_output=True,text=True,timeout=3,check=False)
  if result.returncode: raise PermissionError('trusted macOS identity unavailable')
  label,separator,value=result.stdout.strip().partition(':')
  if label!='GeneratedUID' or not separator: raise PermissionError('invalid macOS GeneratedUID')
  try: generated_uid=str(uuid.UUID(value.strip())).lower()
  except (AttributeError,ValueError): raise PermissionError('invalid macOS GeneratedUID') from None
  return NamedOperatorIdentity(generated_uid,uid)
