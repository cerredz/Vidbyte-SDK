from __future__ import annotations

from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class ExistsTool(FileSystemTool):
    """Check whether a scoped path exists, returning "true" or "false" as output."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for checking path existence.
        return ToolSpec(
            name="exists",
            description="Check whether a file or directory exists at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to check."),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Resolve the scoped path and return its existence as a lowercase boolean string.
        path = call.arguments.get("path", "")
        try:
            target = self._path(path)
            return ToolResult.success(self.name, str(target.exists()).lower(), metadata={"path": str(target)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "ExistsTool",
]
