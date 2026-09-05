"""Trusted installation/operator binding; request strings are not authority."""
from dataclasses import dataclass
import hashlib
import os,pwd,subprocess,uuid
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
 def first_bind(self, occurred_at):
  identity=self.resolver(); iid=self.installation_id()
  if not isinstance(identity,NamedOperatorIdentity) or not identity.generated_uid: raise PermissionError('trusted identity required')
  with self.db._connection:
   if self.db._connection.execute('SELECT 1 FROM installation_operator_binding WHERE installation_id=?',(iid,)).fetchone():raise PermissionError('already bound')
   self.db._connection.execute('INSERT INTO installation_operator_binding VALUES (?,?,?,?,?,?)',(iid,identity.generated_uid,identity.uid,1,'ACTIVE',occurred_at))
   self._audit(iid,identity,'FIRST_BIND',occurred_at,'ALLOW')
  return self.context()
 def context(self):
  identity=self.resolver(); iid=self.installation_id(); row=self.db._connection.execute('SELECT * FROM installation_operator_binding WHERE installation_id=?',(iid,)).fetchone()
  if not row or row['status']!='ACTIVE' or (row['generated_uid'],row['uid'])!=(identity.generated_uid,identity.uid):raise PermissionError('binding denied')
  return OperatorContext(iid,identity.generated_uid,row['version'])
 def authorize(self, context):
  try:return isinstance(context,OperatorContext) and context==self.context()
  except PermissionError:return False
 def revoke(self, context):
  if not self.authorize(context):raise PermissionError('denied')
  with self.db._connection:
   self.db._connection.execute("UPDATE installation_operator_binding SET status='REVOKED',version=version+1 WHERE installation_id=?",(context.installation_id,))
   self._audit(context.installation_id,NamedOperatorIdentity(context.generated_uid,0),'REVOKE','SYSTEM','ALLOW')
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
