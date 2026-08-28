from __future__ import annotations

from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class MakeDirTool(FileSystemTool):
    """Create a scoped directory, optionally creating parent directories."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for creating directories.
        return ToolSpec(
            name="make_dir",
            description="Create a directory at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path of the directory to create."),
                ToolParameter(name="parents", type="boolean", description="Create parent directories if they do not exist.", required=False),
                ToolParameter(name="exist_ok", type="boolean", description="Do not raise an error if the directory already exists.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Resolve the path, create the directory with optional parent creation, and return the path.
        path = call.arguments.get("path", "")
        parents = bool(call.arguments.get("parents", True))
        exist_ok = bool(call.arguments.get("exist_ok", True))
        try:
            self._require_write()
            target = self._path(path)
            self.backend.make_dir(target, parents=parents, exist_ok=exist_ok)
            return ToolResult.success(self.name, str(target), metadata={"path": str(target)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))
