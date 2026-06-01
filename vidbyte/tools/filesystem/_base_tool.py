from __future__ import annotations

from pathlib import Path

from vidbyte.lib.dataclasses import FileSystemToolConfig
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.lib.tools.filesystem.backends import BaseFileSystemBackend
from vidbyte.tools.base import BaseTool


class FileSystemTool(BaseTool):
    """Abstract base for root-scoped filesystem tools; extends BaseTool for agent compatibility."""

    def __init__(self, config: FileSystemToolConfig) -> None:
        # Store config and eagerly resolve the backend so construction fails fast on bad config.
        self._config = config
        self._backend = config.resolved_backend()

    def _path(self, path: str | Path) -> Path:
        # Resolve and scope-check the caller-supplied path against the configured root.
        return FileSystemPermissions.resolve_scoped_path(self._config, path)

    def _require_write(self) -> None:
        # Raise ToolExecutionError if allow_write is not set on the config.
        FileSystemPermissions.require_write_enabled(self._config)

    @property
    def backend(self) -> BaseFileSystemBackend:
        # Return the resolved backend for subclass use.
        return self._backend


__all__ = [
    "FileSystemTool",
]
