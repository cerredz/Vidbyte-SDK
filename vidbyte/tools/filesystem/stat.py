from __future__ import annotations

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class StatTool(FileSystemTool):
    """Return portable metadata for a scoped path."""

    def run(self, path: str) -> ToolResult:
        target = self._path(path)
        file_stat = self.backend.stat(target)
        return ToolResult(value=file_stat, metadata={"path": str(target)})


__all__ = [
    "StatTool",
]
