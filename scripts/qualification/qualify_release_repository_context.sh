#!/usr/bin/env bash
# Exact delivered controller, real own receipts/filesystem, local GitHub boundary.
set -euo pipefail
source_root="$(cd "$(dirname "$0")/../.." && pwd)"
output="${1:?output directory required}"
mkdir -p "$output"
output="$(cd "$output" && pwd)"
cd "$source_root"
python3 -m unittest discover -s tests -p test_release_repository_context.py -v > "$output/positive.log" 2>&1
python3 -m unittest discover -s tests -p test_production_release_workflow.py -v > "$output/retained-cleanup.log" 2>&1
control="$(mktemp -d "${TMPDIR:-/tmp}/forge-release-context-control-XXXXXX")"
trap 'rm -rf -- "$control"' EXIT
mkdir "$control/scripts"
cp scripts/release_operation.py "$control/scripts/"
# Restore repository inference in the delivered boundary; own release code is unchanged.
python3 - scripts/release_github_context.sh "$control/scripts/release_github_context.sh" <<'PY'
import sys
from pathlib import Path
source = Path(sys.argv[1]).read_text()
needle = ' --repo "$FORGE_RELEASE_REPOSITORY"'
assert source.count(needle) == 4
Path(sys.argv[2]).write_text(source.replace(needle, ''))
PY
set +e
FORGE_RELEASE_TEST_WORKSPACE="$control" PYTHONPATH=tests python3 -m unittest \
  test_release_repository_context.ReleaseRepositoryContextTests.test_published_uses_owning_context_outside_git \
  test_release_repository_context.ReleaseRepositoryContextTests.test_other_real_git_and_conflicting_ambient_context \
  -v > "$output/restored-defect.log" 2>&1
control_exit=$?
set -e
test "$control_exit" -eq 1
grep -Fq 'failed to run git: fatal: not a git repository' "$output/restored-defect.log"
grep -Fq 'WRONG_REPOSITORY_TARGET' "$output/restored-defect.log"
grep -Fq 'FAILED (failures=2)' "$output/restored-defect.log"
rm -rf -- "$control"
test ! -e "$control"
trap - EXIT
python3 - "$output" <<'PY'
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
root = Path.cwd()
files = ['.github/workflows/forge-production-release.yml', 'scripts/release_github_context.sh',
         'scripts/release_operation.py', 'tests/test_release_repository_context.py',
         'tests/test_production_release_workflow.py', 'scripts/qualification/qualify_release_repository_context.sh']
out = Path(sys.argv[1])
record = {
    'assignment_id': 'L3-RELEASE-REPOSITORY-CONTEXT-V1-20261010',
    'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'source_tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
    'result': 'RELEASE_REPOSITORY_CONTEXT_PASS',
    'boundary': 'delivered-controller-local-GitHub-fixture; no live publication',
    'restored_defect': {'exit': 1, 'failures': 2, 'outside_git': 'not a git repository', 'ambient_context': 'WRONG_REPOSITORY_TARGET'},
    'owned_control_cleanup': True,
    'files': {name: sha256((root / name).read_bytes()).hexdigest() for name in files},
    'logs': {name: sha256((out / name).read_bytes()).hexdigest() for name in ['positive.log', 'retained-cleanup.log', 'restored-defect.log']},
}
(out / 'release-repository-context.public.json').write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
PY
