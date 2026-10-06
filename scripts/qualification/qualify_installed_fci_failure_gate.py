"""Prove a failed required positive EP scenario returns a failing suite exit."""
from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    path = Path(__file__).with_name("qualify_installed_http_successor.py")
    spec = importlib.util.spec_from_file_location("installed_fci_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("canonical installed qualifier is unavailable")
    qualifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qualifier)
    original = qualifier.qualified_effect_result

    def corrupt_external_ep_result(*values, **options):
        readback, result, terminal = original(*values, **options)
        result = deepcopy(result)
        result["artifact"]["content"]["result"]["summary"] += " Corrupted external EP bytes."
        return readback, result, terminal

    # Only the external HTTP fixture is faulted. Installed Forge's verifier,
    # runtime, governance, completion and the canonical suite exit remain real.
    qualifier.qualified_effect_result = corrupt_external_ep_result
    sys.argv = [str(path), "--wheel", str(args.wheel),
                "--source-revision", args.source_revision,
                "--output-dir", str(args.output_dir), "--scenario", "effect-read-only"]
    exit_code = qualifier.main()
    report = json.loads((args.output_dir / "installed-http-successor.public.json").read_text())
    if (exit_code != 1 or report.get("result") != "FAIL"
            or report.get("failure", {}).get("scenario") != "effect-read-only"):
        raise RuntimeError("failed required positive scenario did not fail the canonical suite")
    receipt = {"result": "PASS", "control": "FAILED_REQUIRED_POSITIVE_SCENARIO_BLOCKS",
               "scenario": "effect-read-only", "external_fault": "report-byte-digest-mismatch",
               "observed_suite_exit": exit_code, "observed_suite_result": report["result"],
               "source_revision": args.source_revision, "artifact": report["artifact"]}
    (args.output_dir / "installed-fci-failure-gate.public.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
