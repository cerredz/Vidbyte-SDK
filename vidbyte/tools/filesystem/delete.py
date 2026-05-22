from __future__ import annotations

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class DeleteTool(FileSystemTool):
    """Delete a file or directory inside a configured root."""

    def run(self, path: str, *, recursive: bool = False) -> ToolResult:
        self._require_write()
        target = self._path(path)
        if not target.exists():
            raise ToolExecutionError("Path does not exist.", details={"path": str(target)})
        self.backend.delete(target, recursive=recursive)
        return ToolResult(value=True, metadata={"path": str(target), "recursive": recursive})


__all__ = [
    "DeleteTool",
]
