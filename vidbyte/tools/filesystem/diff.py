from __future__ import annotations

from vidbyte.lib.dataclasses import ToolResult
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class DiffTool(FileSystemTool):
    """Create a unified diff for a scoped text file."""

    def run(self, path: str, *, content: str | None = None, other_path: str | None = None) -> ToolResult:
        target = self._path(path)
        FileSystemPermissions.require_existing_file(target)
        if content is None and other_path is None:
            raise ToolExecutionError("DiffTool requires content or other_path.")
        if other_path is not None:
            other = self._path(other_path)
            FileSystemPermissions.require_existing_file(other)
            content = self.backend.read_text(other, encoding=self._config.encoding)
            label = str(other)
        else:
            label = "proposed"
        diff = self.backend.diff_text(target, content or "", encoding=self._config.encoding, label=label)
        return ToolResult(value=diff, metadata={"path": str(target), "other_path": other_path})


__all__ = [
    "DiffTool",
]
