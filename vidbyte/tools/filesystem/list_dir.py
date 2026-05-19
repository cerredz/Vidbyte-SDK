from __future__ import annotations

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.base import ToolResult
from vidbyte.tools.filesystem.base import FileSystemToolConfig, resolve_scoped_path


class ListDirTool:
    """List files and folders inside a configured root."""

    def __init__(self, config: FileSystemToolConfig) -> None:
        self._config = config

    def run(self, path: str = ".") -> ToolResult:
        target = resolve_scoped_path(self._config, path)
        if not target.exists():
            raise ToolExecutionError("Directory does not exist.", details={"path": str(target)})
        if not target.is_dir():
            raise ToolExecutionError("Path is not a directory.", details={"path": str(target)})

        entries = tuple(
            f"{entry.name}/" if entry.is_dir() else entry.name
            for entry in sorted(target.iterdir(), key=lambda item: item.name.lower())
        )
        return ToolResult(value=entries, metadata={"path": str(target)})
