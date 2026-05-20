from __future__ import annotations

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class ListDirTool(FileSystemTool):
    """List files and folders inside a configured root."""

    def run(self, path: str = ".") -> ToolResult:
        target = self._path(path)
        FileSystemPermissions.require_existing_directory(target)
        entries = self.backend.list_dir(target)
        return ToolResult(value=entries, metadata={"path": str(target)})
