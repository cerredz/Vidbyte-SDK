from __future__ import annotations

from pathlib import Path

from vidbyte.tools.base import ToolResult
from vidbyte.tools.filesystem.base import (
    FileSystemToolConfig,
    require_write_enabled,
    resolve_scoped_path,
)


class MakeDirTool:
    """Create a directory inside a configured root."""

    def __init__(self, config: FileSystemToolConfig) -> None:
        self._config = config

    def run(self, path: str, *, parents: bool = True, exist_ok: bool = True) -> ToolResult:
        require_write_enabled(self._config)
        target = resolve_scoped_path(self._config, path)
        target.mkdir(parents=parents, exist_ok=exist_ok)
        return ToolResult(value=Path(target), metadata={"path": str(target)})
