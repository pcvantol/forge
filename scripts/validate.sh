#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import sys
if sys.version_info[:2] != (3, 14):
    raise SystemExit("Forge validation requires Python 3.14.x")
PY

python3 -m compileall -q forge tests
if [[ "${FORGE_WITH_COVERAGE:-0}" == "1" ]]; then
  python3 -m coverage run --concurrency=thread --source=forge -m unittest discover -s tests -v
  python3 -m coverage json -o forge-coverage.json
else
  python3 -m unittest discover -s tests -v
fi
python3 scripts/advance_product_version.py --check
python3 docs/ai-development/validate_projection.py \
  --profile forge \
  --source-commit 6ec3b443c3ab3bdf76c626c2046d3778db570eb0 \
  --extension-identity FORGE_DEVELOPMENT_EXTENSION

python3 - <<'PY'
import json
from pathlib import Path

for directory in (Path("schemas"), Path("examples")):
    for path in sorted(directory.glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))
PY

git diff --check
