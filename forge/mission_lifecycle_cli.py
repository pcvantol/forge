"""Installed CLI adapter for bounded administrative Mission lifecycle repair."""
from __future__ import annotations

import argparse
import json

from forge.mission_cli import _governance, _now
from forge.mission_lifecycle import MissionLifecycleService
from forge.runtime.mission_controller import require_no_controller
from forge.runtime.service import RuntimeServiceLock


def archive_no_dispatch(data_root: str, mission_id: str, *, expected_instance_id: str,
                        expected_revision: int, reason_code: str,
                        correlation_id: str) -> dict[str, object]:
    """Archive one exact quiescent historical no-dispatch Mission."""
    database, repository = _governance(data_root)
    try:
        with require_no_controller(database.path), RuntimeServiceLock(database.path).acquire():
            return MissionLifecycleService(repository).archive_quiescent_no_dispatch(
                mission_id,
                expected_instance_id=expected_instance_id,
                expected_revision=expected_revision,
                reason_code=reason_code,
                correlation_id=correlation_id,
                occurred_at=_now(),
            ).to_dict()
    finally:
        database.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="forge-mission-lifecycle",
        description="Apply one explicit authorized administrative Mission lifecycle operation.",
    )
    parser.add_argument("--data-root", required=True)
    parser.add_argument("operation", choices=("archive-no-dispatch",))
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--expected-instance-id", required=True)
    parser.add_argument("--expected-revision", required=True, type=int)
    parser.add_argument("--reason-code", required=True)
    parser.add_argument("--correlation-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = archive_no_dispatch(
            args.data_root, args.mission_id,
            expected_instance_id=args.expected_instance_id,
            expected_revision=args.expected_revision,
            reason_code=args.reason_code,
            correlation_id=args.correlation_id,
        )
    except (OSError, ValueError, RuntimeError, PermissionError) as error:
        print(json.dumps({"status": "ERROR", "error_type": type(error).__name__}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
