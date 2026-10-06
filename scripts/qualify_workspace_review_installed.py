#!/usr/bin/env python3
"""Qualify the scoped review producer through a noneditable installed Forge wheel."""
from __future__ import annotations

from argparse import ArgumentParser
from hashlib import sha256
from importlib.resources import files
from io import BytesIO, StringIO
import json
from pathlib import Path
import subprocess
import sys
import unittest
from zipfile import ZipFile

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
    if subprocess.check_output(
        ["git", "-C", str(SOURCE), "status", "--porcelain"], text=True,
    ).strip():
        raise AssertionError("source checkout is not clean at the qualified commit")
    if not arguments.wheel.is_file():
        raise AssertionError("qualification wheel is absent")
    wheel_bytes = arguments.wheel.read_bytes()
    if not str(Path(forge.__file__).resolve()).startswith(str(Path(sys.prefix).resolve())):
        raise AssertionError("Forge is not imported from the selected Python environment")
    if Path(forge.__file__).resolve().is_relative_to(SOURCE):
        raise AssertionError("Forge is imported from the source checkout")
    installed_root = Path(forge.__file__).resolve().parent
    tracked_product_files = set(subprocess.check_output(
        ["git", "-C", str(SOURCE), "ls-files", "-z", "--", "forge"],
    ).decode("utf-8").split("\0"))
    wheel_members: set[str] = set()
    with ZipFile(BytesIO(wheel_bytes)) as wheel:
        for name in wheel.namelist():
            if not name.startswith("forge/") or name.endswith("/"):
                continue
            wheel_members.add(name)
            payload = wheel.read(name)
            if name not in tracked_product_files or (SOURCE / name).read_bytes() != payload:
                raise AssertionError("wheel Forge payload differs from tracked exact source: " + name)
            installed = installed_root / name.removeprefix("forge/")
            if not installed.is_file() or installed.read_bytes() != payload:
                raise AssertionError("installed Forge bytes differ from selected wheel: " + name)
        wheel_metadata = [name for name in wheel.namelist()
                          if name.endswith((".dist-info/METADATA", ".dist-info/WHEEL",
                                            ".dist-info/entry_points.txt"))]
        if not any(name.endswith(".dist-info/METADATA") for name in wheel_metadata):
            raise AssertionError("selected wheel has no distribution metadata")
        for name in wheel_metadata:
            installed = installed_root.parent / name
            if not installed.is_file() or installed.read_bytes() != wheel.read(name):
                raise AssertionError("installed Forge metadata differ from selected wheel: " + name)
    if not wheel_members:
        raise AssertionError("selected wheel has no Forge product payload")
    for contract in CONTRACTS:
        packaged = files("forge").joinpath("api", contract).read_bytes()
        if packaged != (SOURCE / "forge" / "api" / contract).read_bytes():
            raise AssertionError("installed contract differs from exact source: " + contract)

    # Product imports are pinned to the installed wheel before adding the
    # source-only synthetic OS, LLM, EP and repository test adapters.
    sys.path.append(str(SOURCE))
    from tests import test_workspace_review_inbox as qualification_tests
    if Path(qualification_tests.__file__).resolve() != SOURCE / "tests/test_workspace_review_inbox.py":
        raise AssertionError("review qualification tests do not come from exact source")
    WorkspaceReviewInboxTests = qualification_tests.WorkspaceReviewInboxTests

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkspaceReviewInboxTests)
    output = StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    product_modules = [
        Path(module.__file__).resolve() for name, module in sys.modules.items()
        if (name == "forge" or name.startswith("forge."))
        and getattr(module, "__file__", None) is not None
    ]
    if any(path.is_relative_to(SOURCE) or "site-packages" not in path.parts
           or not path.is_relative_to(installed_root)
           or "forge/" + str(path.relative_to(installed_root)) not in wheel_members
           for path in product_modules):
        raise AssertionError("a Forge product module came from the source checkout")
    test_modules = [Path(module.__file__).resolve() for name, module in sys.modules.items()
                    if (name == "tests" or name.startswith("tests."))
                    and getattr(module, "__file__", None) is not None]
    if not test_modules or any(not path.is_relative_to(SOURCE / "tests")
                               for path in test_modules):
        raise AssertionError("a qualification test module came from outside exact source")
    receipt = {
        "source_revision": revision,
        "wheel_sha256": sha256(wheel_bytes).hexdigest(),
        "installed_forge": str(Path(forge.__file__).resolve()),
        "installed_noneditable": True,
        "product_modules_checked": len(product_modules),
        "source_test_modules_checked": len(test_modules),
        "wheel_product_files_verified": len(wheel_members),
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
