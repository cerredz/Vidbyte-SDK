from __future__ import annotations

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class TouchTool(FileSystemTool):
    """Create a scoped empty file or update its modified time."""

    def run(self, path: str, *, create_parents: bool = False) -> ToolResult:
        self._require_write()
        target = self._path(path)
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        return ToolResult(value=target, metadata={"path": str(target)})


__all__ = [
    "TouchTool",
]
