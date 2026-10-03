"""Check the installed Forge authority boundary with isolated HTTP test data.

This is a wheel/runtime boundary check. It does not claim live EP acceptance.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.metadata import distribution
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
import unittest

import forge


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 14) or not sys.flags.isolated or sys.flags.optimize:
        raise RuntimeError("installed Action authority check requires isolated assertion-enabled Python 3.14")
    source_root = Path(__file__).resolve().parents[2]
    installed_path = Path(forge.__file__).resolve()
    if installed_path.is_relative_to(source_root):
        raise RuntimeError("Action authority check imported editable Forge source")
    wheel_digest = sha256(args.wheel.read_bytes()).hexdigest()
    direct = json.loads(distribution("forge-autonomy").read_text("direct_url.json") or "{}")
    if direct.get("archive_info", {}).get("hashes", {}).get("sha256") != wheel_digest:
        raise RuntimeError("installed Forge wheel does not match the selected artifact")
    test_file = source_root / "tests" / "test_action_authority.py"
    specification = spec_from_file_location("installed_action_authority_tests", test_file)
    if specification is None or specification.loader is None:
        raise RuntimeError("installed Action authority tests are unavailable")
    module = module_from_spec(specification)
    specification.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    receipt = {
        "status": "BOUNDARY_PASS" if result.wasSuccessful() else "BOUNDARY_FAIL",
        "integrated_ep_acceptance": False,
        "ep_readback": "ISOLATED_HTTP_TEST_SERVER",
        "baseline_readback": "CONTROLLED_REPOSITORY_HEAD",
        "python": ".".join(str(item) for item in sys.version_info[:3]),
        "source_revision": args.source_revision,
        "wheel_sha256": wheel_digest,
        "tests_run": result.testsRun,
        "failures": len(result.failures) + len(result.errors),
    }
    args.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
