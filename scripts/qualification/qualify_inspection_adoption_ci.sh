#!/usr/bin/env bash
# Same native isolation as the qualified producer, on the normal disposable hosted runner only.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "${RUNNER_ENVIRONMENT:-}" = github-hosted
test "${RUNNER_OS:-}" = Linux
qualification_source="$(pwd)"
qualification_root="$RUNNER_TEMP/forge-inspection-adoption-ci"
mkdir "$qualification_root" "$qualification_root/ep-source" "$qualification_root/forge-wheel" "$qualification_root/ep-wheel"
curl --fail --location --max-time 60 \
  https://codeload.github.com/pcvantol/engineering-platform/tar.gz/f3b56303b561a7193965f4aa41fd8da744a8c1c2 \
  --output "$qualification_root/ep-source.tar.gz"
tar -xzf "$qualification_root/ep-source.tar.gz" --strip-components=1 -C "$qualification_root/ep-source"
python -m pip wheel "$qualification_root/ep-source" --no-deps --wheel-dir "$qualification_root/ep-wheel"
python -m pip wheel . --no-deps --wheel-dir "$qualification_root/forge-wheel"
python -m venv "$qualification_root/ep-installed"
python -m venv "$qualification_root/forge-installed"
"$qualification_root/ep-installed/bin/python" -m pip install --no-deps "$qualification_root/ep-wheel/engineering_platform-2.3.121-py3-none-any.whl"
qualification_wheels=("$qualification_root"/forge-wheel/forge_autonomy-*.whl)
test "${#qualification_wheels[@]}" -eq 1
"$qualification_root/forge-installed/bin/python" -m pip install --no-deps "${qualification_wheels[0]}"
"$qualification_root/forge-installed/bin/python" -m pip install jsonschema==4.26.0
npm install --prefix "$qualification_root/native" --ignore-scripts --no-audit --no-fund @openai/codex@0.160.1
# Reuse the exact qualified EP hosted-host preparation, not a local host override.
bash "$qualification_root/ep-source/tools/qualification/prepare_ci_native_sandbox.sh"
cd "$RUNNER_TEMP"
"$qualification_root/forge-installed/bin/python" -I \
  "$qualification_source/scripts/qualification/qualify_installed_inspection_content.py" \
  --python "$qualification_root/forge-installed/bin/python" \
  --wheel "${qualification_wheels[0]}" \
  --source-revision "$(git -C "$qualification_source" rev-parse HEAD)" \
  --ep-python "$qualification_root/ep-installed/bin/python" \
  --ep-wheel "$qualification_root/ep-wheel/engineering_platform-2.3.121-py3-none-any.whl" \
  --ep-native-launcher "$qualification_root/native/node_modules/.bin/codex" \
  --output-dir "$qualification_root/proof" --modeled-os-identity
