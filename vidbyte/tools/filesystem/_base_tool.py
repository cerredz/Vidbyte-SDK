from __future__ import annotations

from pathlib import Path

from vidbyte.lib.dataclasses import FileSystemToolConfig
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.lib.tools.filesystem.backends import BaseFileSystemBackend
from vidbyte.tools.base import BaseTool

# The most diff lines an edit tool shows before it cuts the rest.
EDIT_DIFF_MAX_LINES = 80


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

    def _edit_diff(self, target: Path, new_content: str) -> str:
        # Diff new_content against the file still on disk, cut at
        # EDIT_DIFF_MAX_LINES. Edit tools call this before they write.
        try:
            diff = self.backend.diff_text(target, new_content, encoding=self._config.encoding, label=str(target))
        except UnicodeDecodeError:
            return f"no diff: the old file is not valid {self._config.encoding} text"
        if not diff:
            return "no changes"
        # Split on newlines only: splitlines() would also split on a
        # form feed inside a line.
        lines = diff.removesuffix("\n").split("\n")
        if len(lines) > EDIT_DIFF_MAX_LINES:
            lines = [*lines[:EDIT_DIFF_MAX_LINES], f"[diff truncated: {len(lines) - EDIT_DIFF_MAX_LINES} more lines]"]
        return "\n".join(lines)

    @property
    def backend(self) -> BaseFileSystemBackend:
        # Return the resolved backend for subclass use.
        return self._backend


__all__ = [
    "FileSystemTool",
]
