#!/usr/bin/env bash
# Actual qualified producer on the normal disposable hosted runner.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "${RUNNER_ENVIRONMENT:-}" = github-hosted
test "${RUNNER_OS:-}" = Linux
qualification_source="$(pwd)"
qualification_root="$RUNNER_TEMP/forge-genesis-apply-ci"
qualification_ep_sha=4d0c0461d7a5ec7fb7a50aa42f775cc4be09faa5
mkdir "$qualification_root" "$qualification_root/ep-source" "$qualification_root/forge-wheel" "$qualification_root/ep-wheel"
git -C "$qualification_root/ep-source" init -q
git -C "$qualification_root/ep-source" remote add origin https://github.com/pcvantol/engineering-platform.git
git -C "$qualification_root/ep-source" fetch --depth=1 origin "$qualification_ep_sha"
git -C "$qualification_root/ep-source" checkout --detach FETCH_HEAD
test "$(git -C "$qualification_root/ep-source" rev-parse HEAD)" = "$qualification_ep_sha"
test "$(git -C "$qualification_root/ep-source" rev-parse 'HEAD^{tree}')" = b095ba006beccd79171115a7deab55ef7b7c4ff9
python "$qualification_root/ep-source/tools/qualification/build_platform_wheel.py" --source-root "$qualification_root/ep-source" --version 2.3.123 --wheel-directory "$qualification_root/ep-wheel"
python -m pip wheel . --no-deps --wheel-dir "$qualification_root/forge-wheel"
# Exclusive short runtime and scratch names retain the owning finite placement policy.
if test ! -d /private/tmp; then sudo install -d -m1777 /private/tmp; fi
test ! -e /private/tmp/g57
python -m venv /private/tmp/g57
python -m venv "$qualification_root/forge-installed"
/private/tmp/g57/bin/python -m pip install --no-deps "$qualification_root/ep-wheel/engineering_platform-2.3.123-py3-none-any.whl"
qualification_wheels=("$qualification_root"/forge-wheel/forge_autonomy-*.whl)
test "${#qualification_wheels[@]}" -eq 1
"$qualification_root/forge-installed/bin/python" -m pip install --no-deps "${qualification_wheels[0]}"
"$qualification_root/forge-installed/bin/python" -m pip install jsonschema==4.26.0
npm install --prefix "$qualification_root/native" --ignore-scripts --no-audit --no-fund @openai/codex@0.160.1
mkdir "$qualification_root/native/bin"
python - "$qualification_root/native" <<'NATIVE'
from pathlib import Path
import os,sys
root=Path(sys.argv[1])
found=[p for p in (root/'node_modules/@openai').rglob('codex') if '/vendor/' in str(p) and p.is_file() and os.access(p,os.X_OK)]
if len(found)!=1:raise SystemExit('one genuine platform native executable required')
(root/'bin/codex').symlink_to(found[0].resolve())
NATIVE
bash "$qualification_root/ep-source/tools/qualification/prepare_ci_native_sandbox.sh"
qualification_index=70
for qualification_boundary in source-r54 source-r56 verify registered concurrent-late revoke-accept expire-accept revoke-gitref before-revoke before-expire target-race reservation uncertain partial; do
  qualification_index=$((qualification_index+1))
  qualification_flags=()
  case "$qualification_boundary" in
    source-r54) qualification_flags=(--crash-boundary ACCEPT --source-change R54);;
    source-r56) qualification_flags=(--crash-boundary GIT_REF --source-change R56);;
    verify) qualification_flags=(--crash-boundary VERIFY_COMMIT --security-matrix);;
    registered) qualification_flags=(--crash-boundary REGISTER --extended-matrix);;
    concurrent-late) qualification_flags=(--concurrent --late-publication);;
    revoke-accept) qualification_flags=(--crash-boundary ACCEPT --authority-fault REVOKE);;
    expire-accept) qualification_flags=(--crash-boundary ACCEPT --authority-fault EXPIRE --ep-ttl 30);;
    revoke-gitref) qualification_flags=(--crash-boundary GIT_REF --authority-fault REVOKE);;
    before-revoke) qualification_flags=(--before-refusal REVOKE);;
    before-expire) qualification_flags=(--before-refusal EXPIRE --ep-ttl 30);;
    target-race) qualification_flags=(--before-refusal TARGET_RACE);;
    reservation) qualification_flags=(--crash-boundary ACCEPT --reservation-race);;
    uncertain) qualification_flags=(--interruption-step PREFLIGHT);;
    partial) qualification_flags=(--interruption-step WRITE_FILES);;
    *) exit 2;;
  esac
  "$qualification_root/forge-installed/bin/python" -I \
    "$qualification_source/scripts/qualification/qualify_installed_genesis_apply.py" \
    --python "$qualification_root/forge-installed/bin/python" --wheel "${qualification_wheels[0]}" \
    --source-revision "$(git -C "$qualification_source" rev-parse HEAD)" \
    --ep-python /private/tmp/g57/bin/python \
    --ep-wheel "$qualification_root/ep-wheel/engineering_platform-2.3.123-py3-none-any.whl" \
    --ep-wheel-sha256 bc49e7a3b15c9021b16546a5ca96e5fbf280072d900d8d3dc173dee4b79d5b9e \
    --ep-source-revision "$qualification_ep_sha" --ep-source-tree b095ba006beccd79171115a7deab55ef7b7c4ff9 \
    --ep-source-root "$qualification_root/ep-source" --ep-native "$qualification_root/native" \
    --external-validator "$qualification_source/forge/project_bootstrap/assets/validate.py" \
    --output-dir "$qualification_root/proof-$qualification_boundary" --scratch-root "/private/tmp/h$qualification_index" \
    --modeled-os-identity "${qualification_flags[@]}"
done
