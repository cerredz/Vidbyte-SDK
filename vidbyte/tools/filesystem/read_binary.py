from __future__ import annotations

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class ReadBinaryTool(FileSystemTool):
    """Read a binary file inside a configured root."""

    def run(self, path: str) -> ToolResult:
        target = self._path(path)
        FileSystemPermissions.require_existing_file(target)
        return ToolResult(value=self.backend.read_binary(target), metadata={"path": str(target)})


__all__ = [
    "ReadBinaryTool",
]
