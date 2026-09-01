#!/usr/bin/env bash
set -euo pipefail

python3 -m compileall -q forge tests
python3 -m unittest discover -s tests -v
python3 docs/ai-development/validate_projection.py \
  --profile forge \
  --source-commit ec070e399ff4dbd92e760370002995fe4f4d52d6 \
  --extension-identity FORGE_DEVELOPMENT_EXTENSION

python3 - <<'PY'
import json
from pathlib import Path

for directory in (Path("schemas"), Path("examples")):
    for path in sorted(directory.glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))
PY

git diff --check
