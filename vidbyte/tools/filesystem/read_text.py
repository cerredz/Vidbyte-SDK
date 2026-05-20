from __future__ import annotations

from vidbyte.lib.dataclasses import ToolResult
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class ReadTextTool(FileSystemTool):
    """Read a text file inside a configured root."""

    def run(self, path: str) -> ToolResult:
        target = self._path(path)
        FileSystemPermissions.require_existing_file(target)
        return ToolResult(
            value=self.backend.read_text(target, encoding=self._config.encoding),
            metadata={"path": str(target), "encoding": self._config.encoding},
        )
