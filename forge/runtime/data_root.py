"""Canonical, side-effect-free resolution of Forge-owned runtime storage.

This is deliberately the only place that chooses a writable location for an
installed Forge runtime.  Resolving a root is a read-only operation; creation
belongs to :class:`forge.runtime.RuntimeBootstrap`.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Mapping


class DataRootError(RuntimeError):
    """The requested Forge data root is not a safe explicit location."""


class DataRootResolver:
    """Resolve ``--data-root``, ``FORGE_DATA_ROOT``, then the native default."""

    def __init__(self, *, cli_data_root: Path | str | None = None,
                 environment: Mapping[str, str] | None = None,
                 platform: str | None = None, home: Path | str | None = None) -> None:
        self._cli_data_root = cli_data_root
        self._environment = os.environ if environment is None else environment
        self._platform = sys.platform if platform is None else platform
        self._home = None if home is None else Path(home)

    def resolve(self) -> Path:
        candidate = self._cli_data_root
        if candidate is None:
            candidate = self._environment.get("FORGE_DATA_ROOT")
        if candidate is not None and str(candidate).strip():
            return Path(candidate).expanduser().resolve()
        return self.native_default()

    def native_default(self) -> Path:
        home = (self._home or Path(self._environment.get("HOME", str(Path.home())))).expanduser()
        if self._platform == "darwin":
            return (home / "Library" / "Application Support" / "Forge Server").resolve()
        if self._platform.startswith("win"):
            base = self._environment.get("LOCALAPPDATA")
            return (Path(base) if base else home / "AppData" / "Local") .joinpath("Forge Server").resolve()
        base = self._environment.get("XDG_DATA_HOME")
        return (Path(base) if base else home / ".local" / "share").joinpath("forge-server").resolve()


RUNTIME_DIRECTORIES = ("instance", "artifacts", "journals", "logs", "backups", "cache", "locks")
