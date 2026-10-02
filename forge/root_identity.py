"""Detect replacement of a running listener's selected private data root."""
from __future__ import annotations

import os
from pathlib import Path
import stat


class RootIdentity:
    """Pin a root's directory identity for checks at listener entry boundaries."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._identity = self._read_identity()

    def _read_identity(self) -> tuple[int, int] | None:
        try:
            current = os.stat(self.root, follow_symlinks=False)
        except OSError:
            return None
        if not stat.S_ISDIR(current.st_mode):
            return None
        return current.st_dev, current.st_ino

    def drifted(self) -> bool:
        return self._read_identity() != self._identity
