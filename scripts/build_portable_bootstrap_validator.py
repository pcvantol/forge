"""Reproduce finite portable validator from shared original sources; default checks only."""
from pathlib import Path
import json,hashlib,re
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
root=Path(__file__).resolve().parents[1];p=root/'forge/project_bootstrap/assets'
# Original authored shared implementation is embedded, not imported from proposal-controlled paths.
blocks=[]
for src in [root/'forge/project_bootstrap/schema.py',p/'safe_io.py',p/'render_core.py']:
 blocks.append('\n'.join(x for x in src.read_text().splitlines() if not x.startswith(('from __future__','from ..schema'))))
files={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(p.iterdir()) if x.name not in {'catalog.json','validate.py'} and x.is_file()}
c=json.loads((p/'catalog.json').read_text());c['assets']=files.copy();projection=json.dumps(c,sort_keys=True,separators=(',',':'))+'\n'
validator='"""Self-contained portable validator; trusted entrypoint pinned by generated wrapper."""\nimport sys\nimport hashlib\nsys.dont_write_bytecode = True\n'+'\n\n'.join(blocks)
validator+='\n\nEXPECTED_ASSETS = '+repr(files)+'\nEXPECTED_CATALOG_PROJECTION = '+repr(hashlib.sha256(projection.encode()).hexdigest())+'\n'
validator+='''

def check(root):
    if sys.version_info[:2] != (3,14):
        raise ContractError('Python 3.14 required')
    actual = finite_tree(root)
    base = root / BASE_PATH
    catalog_raw, _ = read_regular(base / 'catalog.json')
    catalog = load_json(catalog_raw)
    projection = dict(catalog)
    projection['assets'] = dict(catalog['assets'])
    projection['assets'].pop('validate.py', None)
    if hashlib.sha256(canonical(projection)).hexdigest() != EXPECTED_CATALOG_PROJECTION:
        raise ContractError('trusted catalog projection mismatch')
    selected = {}
    for name, expected_hash in catalog['assets'].items():
        if name != 'validate.py' and EXPECTED_ASSETS.get(name) != expected_hash:
            raise ContractError('unsupported asset binding')
        raw, _ = read_regular(base / name)
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ContractError('baseline asset mismatch')
        selected[name] = raw
    input_raw, _ = read_regular(root / 'engineering/render-input.json')
    value = load_json(input_raw)
    validate(value, load_json(selected['input.schema.json']))
    identity=value['identity']
    if (value['role']=='authority') != (identity['repository_id']==identity['authority_repository_id']):
        raise ContractError('identity conflict')
    if (value['mode']=='GENESIS') != (value['host_profile']=='LOCAL_POSIX'):
        raise ContractError('mode/profile conflict')
    if value['authority_contract_reference'] != identity['authority_repository_id'] + ':engineering/project-contract.json':
        raise ContractError('authority reference conflict')
    def digest(raw):
        return hashlib.sha256(raw).hexdigest()
    def safe_path(name):
        p=PurePosixPath(name)
        if not name or p.is_absolute() or str(p)!=name or '\\\\' in name or not name.isascii() or any(x in {'.','..','.git'} for x in p.parts):
            raise ContractError('unsafe path')
    expected = render(value,catalog,selected,digest(selected['render_core.py']),canonical,load_json,safe_path,digest)
    if actual != set(expected):
        raise ContractError('finite required inventory')
    for name, expected_bytes in expected.items():
        raw, mode = read_regular(root / name)
        if raw != expected_bytes or mode != 0o644:
            raise ContractError('artifact bytes or modes')
    return {'state':'VALIDATED_PROPOSAL','manifest_digest':load_json(expected['engineering/bootstrap-manifest.json'])['manifest_digest'],'product_code_coverage':'NOT_APPLICABLE_NO_PRODUCT_CODE','artifacts':len(actual)}


if __name__=='__main__':
    try:
        if len(sys.argv)!=2:
            raise ContractError('one explicit bundle path required')
        print(json.dumps(check(Path(sys.argv[1])),sort_keys=True))
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({'state':'INVALID_PROPOSAL','error':str(error)},sort_keys=True))
        sys.exit(1)
'''
if args.write:
 (p/'validate.py').write_text(validator)
else:
 assert (p/'validate.py').read_text()==validator, 'portable validator drift'
c['assets']['validate.py']=hashlib.sha256(validator.encode()).hexdigest();raw=json.dumps(c,sort_keys=True,separators=(',',':'))+'\n';
if args.write:(p/'catalog.json').write_text(raw)
else:assert (p/'catalog.json').read_text()==raw, 'catalog drift'
s=root/'forge/project_bootstrap/service.py';updated=re.sub(r'CATALOG_DIGEST = "[0-9a-f]+"','CATALOG_DIGEST = "'+hashlib.sha256(raw.encode()).hexdigest()+'"',s.read_text())
if args.write:s.write_text(updated)
else:assert s.read_text()==updated, 'catalog anchor drift'
