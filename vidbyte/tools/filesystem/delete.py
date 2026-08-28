from __future__ import annotations

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class DeleteTool(FileSystemTool):
    """Delete a scoped file or directory, with optional recursive deletion for directories."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for deleting files or directories.
        return ToolSpec(
            name="delete",
            description="Delete a file or directory at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to delete."),
                ToolParameter(name="recursive", type="boolean", description="Recursively delete a directory and its contents.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Require write permission, verify the path exists, delete it, and return the path.
        path = call.arguments.get("path", "")
        recursive = bool(call.arguments.get("recursive", False))
        try:
            self._require_write()
            target = self._path(path)
            if not target.exists():
                raise ToolExecutionError("Path does not exist.", details={"path": str(target)})
            self.backend.delete(target, recursive=recursive)
            return ToolResult.success(self.name, str(target), metadata={"path": str(target), "recursive": recursive})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "DeleteTool",
]
