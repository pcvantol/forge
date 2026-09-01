#!/usr/bin/env bash
set -euo pipefail

python3 -m compileall -q forge tests
python3 -m unittest discover -s tests -v

python3 - <<'PY'
import json
from pathlib import Path

for directory in (Path("schemas"), Path("examples")):
    for path in sorted(directory.glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))
PY

git diff --check
