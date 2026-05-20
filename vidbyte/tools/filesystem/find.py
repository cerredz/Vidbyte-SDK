from __future__ import annotations

from vidbyte.lib.dataclasses import ToolResult
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class FindTool(FileSystemTool):
    """Find files or directories by glob pattern under a scoped root."""

    def run(self, pattern: str, *, root: str = ".") -> ToolResult:
        target_root = self._path(root)
        FileSystemPermissions.require_existing_directory(target_root)
        matches = self.backend.find(target_root, pattern)
        return ToolResult(value=matches, metadata={"root": str(target_root), "pattern": pattern})


__all__ = [
    "FindTool",
]
