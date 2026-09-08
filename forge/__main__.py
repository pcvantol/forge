"""Read-only command entrypoint for the packaged Forge runtime."""
from __future__ import annotations

import argparse

from ._version import canonical_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Forge mission planning and evidence interpretation runtime.",
    )
    parser.add_argument("--version", action="version", version=canonical_version())
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
