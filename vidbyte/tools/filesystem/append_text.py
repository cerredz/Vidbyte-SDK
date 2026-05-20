from __future__ import annotations

from pathlib import Path

from vidbyte.lib.dataclasses import ToolResult
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class AppendTool(FileSystemTool):
    """Append text to a file inside a configured root."""

    def run(self, path: str, content: str, *, create_parents: bool = False) -> ToolResult:
        self._require_write()
        target = self._path(path)
        self.backend.append_text(target, content, encoding=self._config.encoding, create_parents=create_parents)
        return ToolResult(value=Path(target), metadata={"path": str(target), "encoding": self._config.encoding})


__all__ = [
    "AppendTool",
]
