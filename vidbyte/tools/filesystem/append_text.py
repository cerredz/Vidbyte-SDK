from __future__ import annotations

from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class AppendTool(FileSystemTool):
    """Append text to a scoped file, creating parent directories if requested."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for appending text to files.
        return ToolSpec(
            name="append_text",
            description="Append text content to an existing or new file at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to append to."),
                ToolParameter(name="content", type="string", description="Text content to append."),
                ToolParameter(name="create_parents", type="boolean", description="Create parent directories if they do not exist.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Extract arguments, append to the file, and return the resolved path on success.
        path = call.arguments.get("path", "")
        content = call.arguments.get("content", "")
        create_parents = bool(call.arguments.get("create_parents", False))
        try:
            self._require_write()
            target = self._path(path)
            self.backend.append_text(target, content, encoding=self._config.encoding, create_parents=create_parents)
            return ToolResult.success(self.name, str(target), metadata={"path": str(target), "encoding": self._config.encoding})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "AppendTool",
]
