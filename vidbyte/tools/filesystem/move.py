from __future__ import annotations

from pathlib import Path

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class MoveTool(FileSystemTool):
    """Move or rename a file or directory inside a configured root."""

    def run(self, source: str, destination: str) -> ToolResult:
        self._require_write()
        source_path = self._path(source)
        destination_path = self._path(destination)
        if source_path.is_dir():
            FileSystemPermissions.require_existing_directory(source_path)
        else:
            FileSystemPermissions.require_existing_file(source_path)
        self.backend.move(source_path, destination_path)
        return ToolResult(value=Path(destination_path), metadata={"source": str(source_path), "destination": str(destination_path)})


RenameTool = MoveTool


__all__ = [
    "MoveTool",
    "RenameTool",
]
