from __future__ import annotations

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class ReadLinesTool(FileSystemTool):
    """Read a bounded line window from a scoped text file."""

    def run(self, path: str, *, start: int = 1, end: int | None = None) -> ToolResult:
        if start < 1:
            raise ToolExecutionError("ReadLinesTool start must be at least 1.")
        if end is not None and end < start:
            raise ToolExecutionError("ReadLinesTool end must be greater than or equal to start.")
        target = self._path(path)
        FileSystemPermissions.require_existing_file(target)
        lines = self.backend.read_text(target, encoding=self._config.encoding).splitlines()
        selected = lines[start - 1 : end]
        return ToolResult(value=tuple(selected), metadata={"path": str(target), "start": start, "end": end})


__all__ = [
    "ReadLinesTool",
]
