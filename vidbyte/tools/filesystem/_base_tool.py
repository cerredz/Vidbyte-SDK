from __future__ import annotations

from pathlib import Path

from vidbyte.lib.dataclasses import FileSystemToolConfig
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.lib.tools.filesystem.backends import BaseFileSystemBackend


class FileSystemTool:
    """Base class for root-scoped filesystem tools."""

    def __init__(self, config: FileSystemToolConfig) -> None:
        self._config = config
        self._backend = config.resolved_backend()

    def _path(self, path: str | Path) -> Path:
        return FileSystemPermissions.resolve_scoped_path(self._config, path)

    def _require_write(self) -> None:
        FileSystemPermissions.require_write_enabled(self._config)

    @property
    def backend(self) -> BaseFileSystemBackend:
        return self._backend


__all__ = [
    "FileSystemTool",
]
