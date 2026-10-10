from __future__ import annotations

import re
from pathlib import Path, PurePath

from vidbyte.lib.dataclasses import FileSystemToolConfig
from vidbyte.lib.errors import ToolExecutionError


class FileSystemPermissions:
    """Central path and permission checks for filesystem tools."""

    @staticmethod
    def resolve_scoped_path(config: FileSystemToolConfig, path: str | Path) -> Path:
        root = config.resolved_root()
        requested = (root / Path(path)).expanduser().resolve()
        if requested != root and root not in requested.parents:
            raise ToolExecutionError(
                "Filesystem tool path escaped the configured root.",
                details={"root": str(root), "path": str(path)},
            )
        return requested

    @staticmethod
    def require_pattern_inside_root(pattern: str) -> None:
        # @intent find-pattern-stays-inside-root
        # pathlib globs treat ".." literally, so a pattern with a ".." segment or an anchor would
        # list entries outside the configured root even though the search root itself is scoped.
        if PurePath(pattern).anchor or ".." in re.split(r"[\\/]", pattern):
            raise ToolExecutionError(
                "Filesystem tool glob pattern escaped the configured root.",
                details={"pattern": pattern},
            )

    @staticmethod
    def require_write_enabled(config: FileSystemToolConfig) -> None:
        if not config.allow_write:
            raise ToolExecutionError("Filesystem writes require allow_write=True.")

    @staticmethod
    def require_existing_file(path: Path) -> None:
        if not path.exists():
            raise ToolExecutionError("File does not exist.", details={"path": str(path)})
        if not path.is_file():
            raise ToolExecutionError("Path is not a file.", details={"path": str(path)})

    @staticmethod
    def require_existing_directory(path: Path) -> None:
        if not path.exists():
            raise ToolExecutionError("Directory does not exist.", details={"path": str(path)})
        if not path.is_dir():
            raise ToolExecutionError("Path is not a directory.", details={"path": str(path)})


__all__ = [
    "FileSystemPermissions",
]
