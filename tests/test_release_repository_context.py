"""Execute delivered release shell against an explicit external GitHub fixture."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

import test_production_release_workflow as owning

RELEASE_OPERATION = owning.RELEASE_OPERATION
release_operation = owning.release_operation


ROOT = RELEASE_OPERATION.parent.parent


def workflow_step(name):
    workflow = (ROOT / '.github/workflows/forge-production-release.yml').read_text()
    block = workflow.split('      - name: ' + name + '\n', 1)[1]
    script = block.split('        run: |\n', 1)[1].split('\n      - ', 1)[0]
    return textwrap.dedent(script)


class ReleaseRepositoryContextTests(unittest.TestCase):
    def fixture(self, root, *, other_git=False):
        owner = owning.ProductionReleaseWorkflowTests()
        fixture = owner._fixture(root, persisted_pending=False)
        work = fixture['work']
        runner = fixture['runner_temp']
        registry = runner / 'forge-registry-readback'
        registry.mkdir()
        shutil.copytree(work / 'published-input', registry / 'release-input')
        journal = registry / 'release-input/release-evidence/operations' / (fixture['operation_id'] + '.json')
        published = release_operation.ReleaseOperation.parse(json.loads(journal.read_text()))
        qualified = release_operation.ReleaseOperation.create(
            operation_id=published.operation_id, version=published.version,
            policy_revision=published.policy_revision, source_revision=published.source_revision,
            artifacts=published.artifacts)
        store = release_operation.ReleaseOperationStore(registry / 'release-input/release-evidence')
        shutil.rmtree(store.root)
        release_operation.prepare_qualified(store, qualified, published.qualification)
        (registry / 'registry-readback-digests.json').write_text(json.dumps({'registry': 'pypi'}))
        (registry / 'release-input/dist/criterion-completion-published.json').write_text('{}')
        # No mocked own transition: registry publication and cleanup use release_operation.py.
        for asset in fixture['assets'].iterdir():
            asset.unlink()
        fake_bin = root / 'fake bin'
        (fake_bin / 'rm').unlink()
        (fake_bin / 'gh').write_text('#!' + sys.executable + '\n' + textwrap.dedent('''\
            import json, os, pathlib, shutil, subprocess, sys
            args = sys.argv[1:]
            repo = os.environ.get('GH_REPO')
            if '--repo' in args:
                i = args.index('--repo'); repo = args[i+1]; del args[i:i+2]
            if not repo:
                result = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True)
                if result.returncode:
                    print('failed to run git: fatal: not a git repository', file=sys.stderr); sys.exit(1)
                repo = result.stdout.strip().removeprefix('https://github.com/').removesuffix('.git')
            target = repo if repo.startswith('github.com/') else os.environ.get('GH_HOST', 'github.com') + '/' + repo
            with open(os.environ['CALL_LOG'], 'a') as log:
                log.write(json.dumps({'target': target, 'args': args}) + '\\n')
            if target != 'github.com/pcvantol/forge':
                print('WRONG_REPOSITORY_TARGET', file=sys.stderr); sys.exit(2)
            assets = pathlib.Path(os.environ['FAKE_GH_ASSETS'])
            action = args[1]
            if args[2] != 'forge-v' + os.environ['VERSION']: sys.exit(3)
            if action == 'view':
                field = args[args.index('--json')+1]
                if field == 'targetCommitish': print(os.environ.get('REMOTE_SOURCE', os.environ['SOURCE_SHA']))
                elif field == 'isDraft': print('false')
                elif field == 'assets': print('\\n'.join(p.name for p in assets.iterdir()))
                else: sys.exit(4)
            elif action == 'download':
                if os.environ.get('DOWNLOAD_ERROR') == '1': sys.exit(9)
                name = args[args.index('--pattern')+1]
                if os.environ.get('DOWNLOAD_PATTERN_ERROR') == name: sys.exit(9)
                directory = pathlib.Path(args[args.index('--dir')+1])
                if not (assets / name).exists(): sys.exit(1)
                shutil.copyfile(assets / name, directory / name)
            elif action == 'upload':
                source = pathlib.Path(args[3]); target = assets / source.name
                if target.exists(): sys.exit(8)
                shutil.copyfile(source, target)
                if os.environ.get('LOST_UPLOAD_RESPONSE') == '1': sys.exit(10)
            elif action == 'edit': pass
            else: sys.exit(5)
        '''))
        env = fixture['environment']
        env.update(GITHUB_WORKSPACE=os.environ.get('FORGE_RELEASE_TEST_WORKSPACE', str(ROOT)), GITHUB_REPOSITORY='pcvantol/forge',
                   GITHUB_SERVER_URL='https://github.com', CALL_LOG=str(root / 'calls.jsonl'))
        env.pop('GH_REPO', None)
        env.pop('GH_HOST', None)
        if other_git:
            subprocess.run(['git', 'init', '-q', str(work)], check=True)
            subprocess.run(['git', '-C', str(work), 'remote', 'add', 'origin', 'https://github.com/other/decoy.git'], check=True)
        fixture.update(registry=registry, registry_journal=journal)
        return fixture

    def run_step(self, fixture, name):
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', workflow_step(name)],
                              cwd=fixture['work'], env=fixture['environment'], capture_output=True,
                              text=True, timeout=30)

    def test_published_uses_owning_context_outside_git(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory))
            result = self.run_step(fixture, 'Persist immutable PyPI readback as PUBLISHED evidence')
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual('PUBLISHED', json.loads(fixture['registry_journal'].read_text())['state'])

    def test_other_real_git_and_conflicting_ambient_context(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory), other_git=True)
            fixture['environment'].update(GH_REPO='other/decoy', GH_HOST='decoy.invalid')
            result = self.run_step(fixture, 'Persist immutable PyPI readback as PUBLISHED evidence')
            self.assertEqual(0, result.returncode, result.stderr)
            calls = [json.loads(line) for line in Path(fixture['environment']['CALL_LOG']).read_text().splitlines()]
            self.assertTrue(calls)
            self.assertTrue(all(call['target'] == 'github.com/pcvantol/forge' for call in calls))


    def published(self, fixture):
        result = self.run_step(fixture, 'Persist immutable PyPI readback as PUBLISHED evidence')
        self.assertEqual(0, result.returncode, result.stderr)

    def stage_complete(self, fixture):
        destination = fixture['work'] / 'published-input'
        shutil.rmtree(destination)
        shutil.copytree(fixture['registry'] / 'release-input', destination)
        readback = fixture['work'] / 'published-readback'
        if readback.exists():
            shutil.rmtree(readback)

    def test_complete_receipt_chain_and_exact_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory), other_git=True)
            fixture['environment'].update(GH_REPO='other/decoy')
            qualified_bytes = fixture['registry_journal'].read_bytes()
            qualified_name = 'forge-release-qualified-2.3.0-' + 'a' * 40 + '.json'
            (fixture['assets'] / qualified_name).write_bytes(qualified_bytes)
            shutil.copytree(fixture['registry'] / 'release-input/dist', fixture['work'] / 'dist')
            shutil.copytree(fixture['registry'] / 'release-input/release-evidence', fixture['work'] / 'release-evidence')
            result = self.run_step(fixture, 'Persist the qualified operation outside the runner before PyPI')
            self.assertEqual(0, result.returncode, result.stderr)
            shutil.rmtree(fixture['runner_temp'] / 'forge-qualified-readback')
            shutil.copytree(fixture['registry'] / 'release-input', fixture['work'] / 'release-input')
            result = self.run_step(fixture, 'Recheck the retained qualified operation before PyPI mutation')
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(qualified_bytes, (fixture['assets'] / qualified_name).read_bytes())
            self.published(fixture)
            original = {p.name: p.read_bytes() for p in fixture['assets'].iterdir()}
            self.published(fixture)
            self.assertEqual(original, {p.name: p.read_bytes() for p in fixture['assets'].iterdir()})
            self.stage_complete(fixture)
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertEqual(0, result.returncode, result.stderr)
            complete = next(fixture['assets'].glob('forge-release-complete-*'))
            values = json.loads(complete.read_text())
            self.assertEqual('RELEASE_COMPLETE', values['state'])
            self.assertEqual(fixture['operation_id'], values['operation_id'])
            self.assertEqual('a' * 40, values['source_revision'])
            final_assets = {p.name: p.read_bytes() for p in fixture['assets'].iterdir()}
            self.stage_complete(fixture)  # new runner gets the retained PUBLISHED artifact
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(final_assets, {p.name: p.read_bytes() for p in fixture['assets'].iterdir()})

    def test_invalid_owning_context_refuses_before_local_or_remote_mutation(self):
        for field, value in [('GITHUB_REPOSITORY', ''), ('GITHUB_REPOSITORY', 'other/decoy'),
                             ('GITHUB_SERVER_URL', ''), ('GITHUB_SERVER_URL', 'https://decoy.invalid')]:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                fixture = self.fixture(Path(directory))
                fixture['environment'][field] = value
                before = fixture['registry_journal'].read_bytes()
                result = self.run_step(fixture, 'Persist immutable PyPI readback as PUBLISHED evidence')
                self.assertNotEqual(0, result.returncode)
                self.assertIn('FORGE_RELEASE_CONTEXT_REFUSED', result.stderr)
                self.assertEqual(before, fixture['registry_journal'].read_bytes())
                self.assertFalse(list(fixture['assets'].iterdir()))
                self.assertFalse(Path(fixture['environment']['CALL_LOG']).exists())

    def test_lost_published_upload_response_restarts_same_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory))
            fixture['environment']['LOST_UPLOAD_RESPONSE'] = '1'
            result = self.run_step(fixture, 'Persist immutable PyPI readback as PUBLISHED evidence')
            self.assertNotEqual(0, result.returncode)
            receipt = next(fixture['assets'].glob('forge-release-published-*'))
            original = receipt.read_bytes()
            fixture['environment'].pop('LOST_UPLOAD_RESPONSE')
            self.published(fixture)
            self.assertEqual(original, receipt.read_bytes())
            self.stage_complete(fixture)
            fixture['environment']['LOST_UPLOAD_RESPONSE'] = '1'
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertNotEqual(0, result.returncode)
            complete = next(fixture['assets'].glob('forge-release-complete-*'))
            retained = complete.read_bytes()
            fixture['environment'].pop('LOST_UPLOAD_RESPONSE')
            self.stage_complete(fixture)
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(retained, complete.read_bytes())

    def test_download_error_does_not_upload_or_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory))
            self.published(fixture)
            original = {p.name: p.read_bytes() for p in fixture['assets'].iterdir()}
            fixture['environment']['DOWNLOAD_ERROR'] = '1'
            result = self.run_step(fixture, 'Persist immutable PyPI readback as PUBLISHED evidence')
            self.assertNotEqual(0, result.returncode)
            self.stage_complete(fixture)
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(original, {p.name: p.read_bytes() for p in fixture['assets'].iterdir()})
            journal = fixture['work'] / 'published-input/release-evidence/operations' / (fixture['operation_id'] + '.json')
            self.assertEqual('PUBLISHED', json.loads(journal.read_text())['state'])

    def test_remote_receipt_conflicts_are_never_overwritten(self):
        for field, value in [('source_revision', 'b' * 40), ('version', '9.9.9'),
                             ('operation_id', 'different-operation'), ('artifacts', {'wheel': 'f' * 64, 'sdist': 'e' * 64}),
                             ('publication_receipt', {'readback': 'different'})]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                fixture = self.fixture(Path(directory))
                self.published(fixture)
                receipt = next(fixture['assets'].glob('forge-release-published-*'))
                values = json.loads(receipt.read_text()); values[field] = value
                receipt.write_text(json.dumps(values))
                conflict = receipt.read_bytes()
                result = self.run_step(fixture, 'Persist immutable PyPI readback as PUBLISHED evidence')
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(conflict, receipt.read_bytes())
                self.stage_complete(fixture)
                result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(list(fixture['assets'].glob('forge-release-complete-*')))

    def test_wrong_remote_tag_source_refuses_complete_before_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory))
            self.published(fixture)
            self.stage_complete(fixture)
            fixture['environment']['REMOTE_SOURCE'] = 'b' * 40
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertNotEqual(0, result.returncode)
            self.assertTrue((fixture['work'] / 'published-input/dist').exists())
            self.assertFalse(list(fixture['assets'].glob('forge-release-complete-*')))


    def test_existing_complete_conflict_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory))
            self.published(fixture)
            self.stage_complete(fixture)
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertEqual(0, result.returncode, result.stderr)
            receipt = next(fixture['assets'].glob('forge-release-complete-*'))
            values = json.loads(receipt.read_text()); values['cleanup']['result'] = 'CONFLICT'
            receipt.write_text(json.dumps(values))
            original = receipt.read_bytes()
            self.stage_complete(fixture)
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(original, receipt.read_bytes())

    def test_retained_pending_download_failure_cannot_be_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory))
            self.published(fixture)
            self.stage_complete(fixture)
            evidence = fixture['work'] / 'published-input/release-evidence'
            store = release_operation.ReleaseOperationStore(evidence)
            current = store.load(fixture['operation_id'])
            pending = release_operation.mark_cleanup_pending(store, current, {'result': 'CLEANUP_PENDING'})
            pending_name = 'forge-cleanup-pending-' + current.version + '-' + current.source_revision + '.json'
            (fixture['assets'] / pending_name).write_bytes((evidence / 'operations' / (current.operation_id + '.json')).read_bytes())
            self.stage_complete(fixture)
            fixture['environment']['DOWNLOAD_PATTERN_ERROR'] = pending_name
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertNotEqual(0, result.returncode)
            self.assertTrue((fixture['work'] / 'published-input/dist').exists())
            self.assertFalse(list(fixture['assets'].glob('forge-release-complete-*')))
            fixture['environment'].pop('DOWNLOAD_PATTERN_ERROR')
            self.stage_complete(fixture)
            result = self.run_step(fixture, 'Complete cleanup after durable PUBLISHED evidence')
            self.assertEqual(0, result.returncode, result.stderr)
            receipt = next(fixture['assets'].glob('forge-release-complete-*'))
            self.assertEqual('RELEASE_COMPLETE', json.loads(receipt.read_text())['state'])
            self.assertEqual(pending.operation_id, json.loads(receipt.read_text())['operation_id'])


if __name__ == '__main__':
    unittest.main()
