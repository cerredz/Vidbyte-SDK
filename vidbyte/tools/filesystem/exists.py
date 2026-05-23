from __future__ import annotations

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class ExistsTool(FileSystemTool):
    """Check whether a scoped path exists."""

    def run(self, path: str) -> ToolResult:
        target = self._path(path)
        return ToolResult(value=target.exists(), metadata={"path": str(target)})


__all__ = [
    "ExistsTool",
]
