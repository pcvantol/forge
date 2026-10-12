"""Real finite renderer, export safety, offline portable checks and CLI refusal."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from forge.project_bootstrap import cli, schema, service


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.value = schema.load_json(Path('examples/project-bootstrap/authority-input.json').read_bytes())
        self.tmp = tempfile.TemporaryDirectory(prefix='forge-pb-test-', dir='/private/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_profiles_roles_and_real_portable_validator(self):
        for mode, role in [('GENESIS','authority'),('GENESIS','child'),('MANAGED','authority'),('MANAGED','child')]:
            v=copy.deepcopy(self.value);v['mode']=mode;v['host_profile']='LOCAL_POSIX' if mode=='GENESIS' else 'GITHUB_DOCUMENTS';v['role']=role
            if role=='child':v['identity']['repository_id']='sample-client'
            target=self.root/(mode+role);service.export(v,target);self.assertEqual(service.check_bundle(target)['state'],'VALIDATED_PROPOSAL')
            files=service.render(v)
            self.assertEqual('docs/product/VISION.md' in files,role=='authority')
            self.assertEqual('.github/workflows/validation.yml' in files,mode=='MANAGED')
            run=subprocess.run([sys.executable,'-I',str(target/service.BASE_PATH/'validate.py'),str(target)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('NOT_APPLICABLE_NO_PRODUCT_CODE',run.stdout)
            self.assertEqual(service.check_bundle(target)['state'],'VALIDATED_PROPOSAL')

    def test_determinism_changed_input_and_no_runtime(self):
        a=service.render(self.value);self.assertEqual(a,service.render(copy.deepcopy(self.value)))
        v=copy.deepcopy(self.value);v['product']['purpose']='Different supplied purpose.'
        self.assertNotEqual(a,service.render(v))
        self.assertFalse(any('runtime.db' in p or '.git/' in p for p in a))
        self.assertNotIn('MISSION-',b''.join(a.values()).decode())

    def test_closed_and_unsupported_input(self):
        bad=[]
        for key, value in [('mode','OTHER'),('baseline','latest'),('document_language','nl'),('stack_profile','PYTHON'),('security_profile','CODEQL'),('host_profile','OTHER')]:
            v=copy.deepcopy(self.value);v[key]=value;bad.append(v)
        v=copy.deepcopy(self.value);v['approval']='APPROVED';bad.append(v)
        v=copy.deepcopy(self.value);v['identity']['project_id']='../../escape';bad.append(v)
        v=copy.deepcopy(self.value);v['identity']['repository_id']='other-child';bad.append(v)
        v=copy.deepcopy(self.value);v['authority_contract_reference']='https://host/remote';bad.append(v)
        v=copy.deepcopy(self.value);v['host_profile']='GITHUB_DOCUMENTS';bad.append(v)
        v=copy.deepcopy(self.value);del v['source_references'];bad.append(v)
        for v in bad:
            with self.assertRaises(schema.ContractError):service.render(v)

    def test_export_no_overwrite_no_symlink_parents(self):
        target=self.root/'bundle';service.export(self.value,target);before=service.render(self.value)
        with self.assertRaises(FileExistsError):service.export(self.value,target)
        self.assertEqual(before,service.render(self.value))
        outside=self.root/'outside';outside.mkdir();link=self.root/'link';link.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(OSError):service.export(self.value,link/'escape')
        self.assertEqual(list(outside.iterdir()),[])
        (target/'malicious').symlink_to(outside)
        with self.assertRaises(schema.ContractError):service.check_bundle(target)
        with self.assertRaises(schema.ContractError):service.check_bundle(link)

    def test_paths_and_malformed_json(self):
        for p in ['../x','/x','a/../x','.git/hooks/run','a//b','a\\b','A/é','x\x00']:
            with self.assertRaises(schema.ContractError):service.safe_path(p)
        for raw in [b'{"a":1,"a":2}',b'NaN',b'\xff',b'{broken']:
            with self.assertRaises(schema.ContractError):schema.load_json(raw)
        self.assertEqual(schema.load_json(b'{"ok":true}'),{'ok':True})

    def test_tampering_actual_negative_control(self):
        target=self.root/'bundle';service.export(self.value,target)
        p=target/'docs/product/VISION.md';p.write_text('tampered')
        with self.assertRaises(schema.ContractError):service.check_bundle(target)
        run=subprocess.run([sys.executable,'-I',str(target/service.BASE_PATH/'validate.py'),str(target)],capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,1);self.assertIn('artifact bytes',run.stdout)
        p.write_bytes(service.render(self.value)['docs/product/VISION.md'])
        self.assertEqual(service.check_bundle(target)['state'],'VALIDATED_PROPOSAL')
        (target/'extra').write_text('not allowed')
        with self.assertRaises(schema.ContractError):service.check_bundle(target)

    def test_catalog_tampering_refusal(self):
        real=service.files
        class Changed:
            def joinpath(self,name):
                self.name=name;return self
            def read_bytes(self):
                return b'{}'
        with patch.object(service,'files',return_value=Changed()):
            with self.assertRaisesRegex(schema.ContractError,'catalog digest'):service.assets()
        self.assertTrue(real('forge.project_bootstrap'))

    def test_cli_actual_commands_errors_and_explicit_export(self):
        source=self.root/'input.json';source.write_bytes(schema.canonical(self.value));target=self.root/'cli-bundle'
        for args in [['catalog'],['validate-input','--input',str(source)],['render','--input',str(source),'--export',str(target)],['check-bundle','--bundle',str(target)]]:
            with contextlib.redirect_stdout(io.StringIO()) as out:self.assertEqual(cli.main(args),0)
            self.assertIsInstance(json.loads(out.getvalue()),dict)
        source.write_bytes(b'{')
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(cli.main(['validate-input','--input',str(source)]),1)
        source.write_bytes(b'x'*131073)
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(cli.main(['validate-input','--input',str(source)]),1)

    def test_schema_closed_dialect(self):
        cases=[(1,{'type':'string'}),(True,{'type':'integer'}),('x',{'type':'string','const':'y'}),('x',{'type':'string','enum':['y']}),({}, {'type':'object'}),([],{'type':'array','minItems':1,'items':{'type':'string'}}),('',{'type':'string','minLength':1}),('x',{'type':'string','pattern':'y'}),(3,{'type':'integer','maximum':2}),(None,{'type':'null','$ref':'https://remote'})]
        for value,rule in cases:
            with self.assertRaises(schema.ContractError):schema.validate(value,rule)
        schema.validate([1],{'type':'array','items':{'type':'integer','minimum':0}})
        schema.validate(None,{'type':'null'})
        from forge.project_bootstrap.assets import schema as exported_schema
        for value,rule in cases:
            with self.assertRaises(exported_schema.ContractError):exported_schema.validate(value,rule)
        exported_schema.validate([1],{'type':'array','items':{'type':'integer'}})
        for raw in [b'{\"a\":1,\"a\":2}',b'NaN',b'\xff',b'{bad']:
            with self.assertRaises(exported_schema.ContractError):exported_schema.load_json(raw)
        self.assertEqual(exported_schema.canonical({'ok':1}),schema.canonical({'ok':1}))
        self.assertEqual(Path('forge/project_bootstrap/schema.py').read_bytes(),Path('forge/project_bootstrap/assets/schema.py').read_bytes())

    def test_bounded_reads_fifo_symlink_and_descriptor_swap(self):
        from forge.project_bootstrap.assets import safe_io
        normal=self.root/'normal';normal.write_bytes(b'original')
        link=self.root/'link';link.symlink_to(normal)
        with self.assertRaises(OSError):safe_io.read_regular(link)
        huge=self.root/'huge';huge.write_bytes(b'x'*131073)
        with self.assertRaises(schema.ContractError):safe_io.read_regular(huge)
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(schema.ContractError):safe_io.read_regular(fifo)
        outside=self.root/'outside';outside.write_bytes(b'outside')
        actual_open=os.open
        def swap(name,flags,*args,**kwargs):
            fd=actual_open(name,flags,*args,**kwargs)
            if name=='normal':
                normal.rename(self.root/'original-retained');normal.symlink_to(outside)
            return fd
        with patch.object(safe_io.os,'open',side_effect=swap):
            self.assertEqual(safe_io.read_regular(normal)[0],b'original')
        self.assertEqual(outside.read_bytes(),b'outside')
        with self.assertRaises(OSError):safe_io.read_regular(normal)

    def test_coherent_authority_tampering_and_modes_rejected(self):
        import hashlib
        target=self.root/'bundle';service.export(self.value,target)
        validator=target/service.BASE_PATH/'validate.py'
        def portable():
            return subprocess.run([sys.executable,'-I',str(validator),str(target)],capture_output=True,text=True,timeout=10)
        original=(target/'engineering/project-contract.json').read_bytes()
        manifest_path=target/'engineering/bootstrap-manifest.json';manifest_original=manifest_path.read_bytes()
        for field,changed in [('state','GENESIS_READY'),('approval','APPROVED'),('validation','true'),('role','child')]:
            contract=json.loads(original);contract[field]=changed;raw=schema.canonical(contract)
            (target/'engineering/project-contract.json').write_bytes(raw)
            manifest=json.loads(manifest_original)
            for entry in manifest['artifacts']:
                if entry['relative_path']=='engineering/project-contract.json':entry['bytes']=len(raw);entry['expected_after_digest']=hashlib.sha256(raw).hexdigest()
            manifest.pop('manifest_digest');manifest['manifest_digest']=hashlib.sha256(schema.canonical(manifest)).hexdigest();manifest_path.write_bytes(schema.canonical(manifest))
            self.assertEqual(portable().returncode,1)
            with self.assertRaises(schema.ContractError):service.check_bundle(target)
        (target/'engineering/project-contract.json').write_bytes(original);manifest_path.write_bytes(manifest_original)
        p=target/'README.md';p.chmod(0o600)
        self.assertEqual(portable().returncode,1)
        with self.assertRaises(schema.ContractError):service.check_bundle(target)
        p.chmod(0o644);self.assertEqual(portable().returncode,0)

    def test_posix_wrapper_validator_and_schema_controls(self):
        target=self.root/'bundle';service.export(self.value,target)
        wrapper=target/'scripts/validate.sh';env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin'}
        good=subprocess.run(['bash',str(wrapper)],env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(good.returncode,0,good.stdout+good.stderr)
        validator=target/service.BASE_PATH/'validate.py';validator.write_text("print('FAKE PASS')\n")
        refused=subprocess.run(['bash',str(wrapper)],env=env,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(refused.returncode,0);self.assertNotIn('FAKE PASS',refused.stdout)
        validator.write_bytes(service.render(self.value)[str(Path(service.BASE_PATH)/'validate.py')])
        schema_file=target/service.BASE_PATH/'schema.py';sentinel=self.root/'executed'
        schema_file.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n")
        refused=subprocess.run(['bash',str(wrapper)],env=env,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(refused.returncode,0);self.assertFalse(sentinel.exists())
        missing=self.root/'tools';missing.mkdir();(missing/'dirname').symlink_to('/usr/bin/dirname')
        refused=subprocess.run(['/bin/sh',str(wrapper)],env={'PATH':str(missing)},capture_output=True,text=True,timeout=10)
        self.assertEqual(refused.returncode,1);self.assertIn('Python 3.14 required',refused.stderr)

    def test_portable_direct_closed_schema_and_trusted_projection(self):
        from forge.project_bootstrap.assets import validate as portable_module
        module=vars(portable_module)
        target=self.root/'bundle';service.export(self.value,target)
        self.assertEqual(module['check'](target)['state'],'VALIDATED_PROPOSAL')
        for mode, role in [('GENESIS','child'),('MANAGED','authority'),('MANAGED','child')]:
            v=copy.deepcopy(self.value);v['mode']=mode;v['host_profile']='LOCAL_POSIX' if mode=='GENESIS' else 'GITHUB_DOCUMENTS';v['role']=role
            if role=='child':v['identity']['repository_id']='sample-client'
            other=self.root/(mode+role);service.export(v,other);self.assertEqual(module['check'](other)['state'],'VALIDATED_PROPOSAL')
        catalog=target/service.BASE_PATH/'catalog.json';raw=catalog.read_bytes();value=json.loads(raw);value['qualification']='RELEASED';catalog.write_bytes(schema.canonical(value))
        with self.assertRaises(ValueError):module['check'](target)
        catalog.write_bytes(raw)
        (target/'engineering/render-input.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):module['check'](target)

    def test_finite_inventory_limit_and_export_traversal(self):
        from forge.project_bootstrap.assets.safe_io import finite_tree
        big=self.root/'big';big.mkdir()
        for i in range(129):(big/str(i)).write_bytes(b'')
        with self.assertRaises(schema.ContractError):finite_tree(big)
        with self.assertRaises(schema.ContractError):service.export(self.value,self.root/'x'/'..'/'escape')
        self.assertFalse((self.root/'escape').exists())


    def test_export_preserves_existing_repository(self):
        repo=self.root/'repo';repo.mkdir();(repo/'.git').write_text('gitdir: retained-history')
        (repo/'README.md').write_text('existing product')
        with self.assertRaises(schema.ContractError):service.export(self.value,repo/'proposal')
        child=repo/'nested';child.mkdir()
        with self.assertRaises(schema.ContractError):service.export(self.value,child/'proposal')
        self.assertEqual((repo/'README.md').read_text(),'existing product')
        self.assertFalse((repo/'proposal').exists());self.assertFalse((child/'proposal').exists())
