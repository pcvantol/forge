"""Fail an ordinary Forge PR when a changed product Python file is under 80.2%."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


THRESHOLD = 80.2


def changed_product_files(base_sha: str) -> list[str]:
    if len(base_sha) != 40 or any(character not in "0123456789abcdef" for character in base_sha):
        raise ValueError("PR base SHA is unavailable or invalid")
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base_sha}...HEAD", "--", "forge"],
        check=True, capture_output=True, text=True,
    )
    return sorted({name for name in result.stdout.splitlines()
                   if name.startswith("forge/") and name.endswith(".py") and Path(name).is_file()})


def check_coverage(report: dict[str, object], changed: list[str]) -> list[str]:
    files = report.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage report has no file data")
    failures = []
    for name in changed:
        entry = files.get(name)
        summary = entry.get("summary") if isinstance(entry, dict) else None
        if not isinstance(summary, dict):
            failures.append(f"{name}: missing coverage")
            continue
        covered, total = summary.get("covered_lines"), summary.get("num_statements")
        if (not isinstance(covered, int) or isinstance(covered, bool)
                or not isinstance(total, int) or isinstance(total, bool)
                or total <= 0 or covered < 0 or covered > total):
            failures.append(f"{name}: invalid executable-line coverage")
            continue
        percent = 100 * covered / total
        print(f"{name}: {covered}/{total} = {percent:.2f}%")
        if percent <= THRESHOLD:
            failures.append(f"{name}: {percent:.2f}% must be >{THRESHOLD}%")
    return failures


def main() -> int:
    try:
        changed = changed_product_files(os.environ.get("FORGE_COVERAGE_BASE_SHA", ""))
        if not changed:
            print("No changed Forge product Python files")
            return 0
        report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        failures = check_coverage(report, changed)
    except (IndexError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Changed-source coverage unavailable: {error}", file=sys.stderr)
        return 1
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
