"""Isolated synthetic owner setup; no live project, provider or repository effect."""
from pathlib import Path
from hashlib import sha256
from datetime import UTC,datetime,timedelta
import json,sys
from forge.runtime.bootstrap import RuntimeBootstrap
from forge.operator_identity import InstallationOperatorService,MacOSGeneratedUIDIdentityAdapter
from forge.project_proposal_grant import ProjectProposalGrant

def configure(root):
    root.mkdir(mode=0o700)
    with RuntimeBootstrap(data_root=root/'runtime',forge_version='synthetic-qualification').open() as db:
        owner=InstallationOperatorService(db,MacOSGeneratedUIDIdentityAdapter().resolve);context=owner.first_bind();instance=db.runtime_identity.runtime_id
        human=sha256(context.generated_uid.encode()).hexdigest()[:16]
    (root/'admin.private').write_text('synthetic-content-qualification-admin');(root/'admin.private').chmod(0o600)
    grant=ProjectProposalGrant(root/'runtime',instance);grant.initialize()
    grant.issue(principal_id='synthetic-service',audience='synthetic-workspace',dossier_ids=['synthetic-dossier'],permissions=['READ','PREPARE'],kinds=['pb-render/1.0'],maximum_records=8,expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=root/'prepare.private')
    return {'instance_id':instance,'human_principal_id':human}

if __name__=='__main__':print(json.dumps(configure(Path(sys.argv[1]))))
