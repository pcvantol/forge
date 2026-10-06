#!/usr/bin/env python3
"""Qualify the scoped review producer through a noneditable installed Forge wheel."""
from __future__ import annotations

from argparse import ArgumentParser
from hashlib import sha256
from importlib.resources import files
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import unittest

import forge
import forge.governed_continuation
import forge.runtime.bootstrap
import forge.runtime.dynamic_mission
import forge.server_runtime
import forge.workspace_review_grant
import forge.workspace_review_inbox


SOURCE = Path(__file__).resolve().parents[1]
CONTRACTS = (
    "workspace-review-inbox-v1.json", "server-openapi-v1.json", "server-postman-v1.json",
)


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-source-revision", required=True)
    arguments = parser.parse_args()
    revision = subprocess.check_output(
        ["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True,
    ).strip()
    if revision != arguments.expected_source_revision:
        raise AssertionError("source revision does not match the qualified commit")
    if not arguments.wheel.is_file():
        raise AssertionError("qualification wheel is absent")
    if not str(Path(forge.__file__).resolve()).startswith(str(Path(sys.prefix).resolve())):
        raise AssertionError("Forge is not imported from the selected Python environment")
    if Path(forge.__file__).resolve().is_relative_to(SOURCE):
        raise AssertionError("Forge is imported from the source checkout")
    for contract in CONTRACTS:
        packaged = files("forge").joinpath("api", contract).read_bytes()
        if packaged != (SOURCE / "forge" / "api" / contract).read_bytes():
            raise AssertionError("installed contract differs from exact source: " + contract)

    # Product imports are pinned to the installed wheel before adding the
    # source-only synthetic OS, LLM, EP and repository test adapters.
    sys.path.append(str(SOURCE))
    from tests.test_workspace_review_inbox import WorkspaceReviewInboxTests

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkspaceReviewInboxTests)
    output = StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    product_modules = [
        Path(module.__file__).resolve() for name, module in sys.modules.items()
        if (name == "forge" or name.startswith("forge."))
        and getattr(module, "__file__", None) is not None
    ]
    if any(path.is_relative_to(SOURCE) or "site-packages" not in path.parts
           for path in product_modules):
        raise AssertionError("a Forge product module came from the source checkout")
    receipt = {
        "source_revision": revision,
        "wheel_sha256": sha256(arguments.wheel.read_bytes()).hexdigest(),
        "installed_forge": str(Path(forge.__file__).resolve()),
        "installed_noneditable": True,
        "product_modules_checked": len(product_modules),
        "contracts_checked": list(CONTRACTS),
        "suite": "WorkspaceReviewInboxTests",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skips": len(result.skipped),
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "test_output": output.getvalue(),
    }
    arguments.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    print(json.dumps({key: value for key, value in receipt.items() if key != "test_output"},
                     sort_keys=True))
    if not result.wasSuccessful():
        print(output.getvalue())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
