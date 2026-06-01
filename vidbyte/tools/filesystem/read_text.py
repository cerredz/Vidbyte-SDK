from __future__ import annotations

from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ReadTextTool(FileSystemTool):
    """Read text content from a scoped file and return it as the tool output."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for reading text files.
        return ToolSpec(
            name="read_text",
            description="Read the full text content of a file at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to read."),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Resolve the path, verify it is an existing file, and return its text content.
        path = call.arguments.get("path", "")
        try:
            target = self._path(path)
            FileSystemPermissions.require_existing_file(target)
            text = self.backend.read_text(target, encoding=self._config.encoding)
            return ToolResult.success(self.name, text, metadata={"path": str(target), "encoding": self._config.encoding})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))
