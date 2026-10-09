"""Bounded private operation intents over canonical worksets, not governance truth."""
import json,os,stat
from .advisory_contract import digest
from .workspace_review_grant import _private_directory, _write_private
from .workset_release_grant import CONTRACT


def private_packet(path,limit=524288):
    """Private bounded packet reader with the same no-follow file protections."""
    _private_directory(path.parent,create=False)
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(descriptor,'rb') as source:
        details=os.fstat(source.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_mode&0o077 or details.st_size>limit:
            raise ValueError('private bounded release packet required')
        return source.read(limit+1)


class ReleaseJournal:
    def __init__(self,root,reference):
        self.reference=reference
        self.path=root/'governance'/'workset-release'/(digest(reference)[7:]+'.json')

    def read(self):
        if not self.path.exists() and not self.path.is_symlink():
            return {'contract_version':CONTRACT,'principal_reference':self.reference,'intents':{},'operations':{}}
        try:d=json.loads(private_packet(self.path))
        except (OSError,ValueError,TypeError):raise RuntimeError('release journal unavailable') from None
        if (not isinstance(d,dict) or set(d)!={'contract_version','principal_reference','intents','operations'}
                or d['contract_version']!=CONTRACT or d['principal_reference']!=self.reference
                or not isinstance(d['intents'],dict) or len(d['intents'])>8
                or not isinstance(d['operations'],dict) or len(d['operations'])>128):
            raise RuntimeError('release journal integrity failed')
        for key,intent in d['intents'].items():
            if (not isinstance(intent,dict) or set(intent)!={'package','package_digest','grant_id','operation_id','created_at'}
                    or digest(intent['package'])!=intent['package_digest']
                    or intent['package']['release_key']!=key
                    or intent['package']['principal_reference']!=self.reference):
                raise RuntimeError('release intent integrity failed')
        for operation,record in d['operations'].items():
            if (not isinstance(record,dict) or set(record)!={'request','request_digest','release_key'}
                    or record['request'].get('operation_id')!=operation
                    or digest(record['request'])!=record['request_digest']
                    or record['release_key'] not in d['intents']):
                raise RuntimeError('release operation integrity failed')
        return d

    def save(self,d):
        if len(d['operations'])>128 or len(d['intents'])>8:
            raise ValueError('release journal capacity exhausted')
        raw=json.dumps(d,sort_keys=True,ensure_ascii=False).encode()
        if len(raw)>524288:raise ValueError('release journal capacity exhausted')
        _write_private(self.path,raw)
