from __future__ import annotations

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ReplaceTextTool(FileSystemTool):
    """Replace the single occurrence of a search string in a scoped text file."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for exact-once in-place text replacement.
        return ToolSpec(
            name="replace_text",
            description="Replace a search string that appears exactly once in a file at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to the file."),
                ToolParameter(name="search", type="string", description="Text to search for (must appear exactly once)."),
                ToolParameter(name="replacement", type="string", description="Text to replace the search string with."),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Read, validate uniqueness of the search string, replace it, and write back.
        path = call.arguments.get("path", "")
        search = call.arguments.get("search", "")
        replacement = call.arguments.get("replacement", "")
        try:
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
            return ToolResult.success(self.name, str(target), metadata={"path": str(target), "replacements": 1})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "ReplaceTextTool",
]
