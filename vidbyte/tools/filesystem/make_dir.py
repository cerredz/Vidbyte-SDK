from __future__ import annotations

from pathlib import Path

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class MakeDirTool(FileSystemTool):
    """Create a directory inside a configured root."""

    def run(self, path: str, *, parents: bool = True, exist_ok: bool = True) -> ToolResult:
        self._require_write()
        target = self._path(path)
        self.backend.make_dir(target, parents=parents, exist_ok=exist_ok)
        return ToolResult(value=Path(target), metadata={"path": str(target)})
