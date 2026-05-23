from __future__ import annotations

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class ReplaceTextTool(FileSystemTool):
    """Replace text in a scoped file when the search text appears exactly once."""

    def run(self, path: str, *, search: str, replacement: str) -> ToolResult:
        self._require_write()
        if not search:
            raise ToolExecutionError("ReplaceTextTool search cannot be empty.")
        target = self._path(path)
        FileSystemPermissions.require_existing_file(target)
        content = self.backend.read_text(target, encoding=self._config.encoding)
        count = content.count(search)
        if count != 1:
            raise ToolExecutionError(
                "ReplaceTextTool requires the search text to appear exactly once.",
                details={"matches": count, "path": str(target)},
            )
        updated = content.replace(search, replacement, 1)
        self.backend.write_text(target, updated, encoding=self._config.encoding, create_parents=False)
        return ToolResult(value=target, metadata={"path": str(target), "replacements": 1})


__all__ = [
    "ReplaceTextTool",
]
