from __future__ import annotations

from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class TouchTool(FileSystemTool):
    """Create an empty scoped file or update its modified time."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for creating or touching a file.
        return ToolSpec(
            name="touch",
            description="Create an empty file or update its modified time at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to touch."),
                ToolParameter(name="create_parents", type="boolean", description="Create parent directories if they do not exist.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Resolve the path, optionally create parents, touch the file, and return the path.
        path = call.arguments.get("path", "")
        create_parents = bool(call.arguments.get("create_parents", False))
        try:
            self._require_write()
            target = self._path(path)
            if create_parents:
                target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
            return ToolResult.success(self.name, str(target), metadata={"path": str(target)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "TouchTool",
]
