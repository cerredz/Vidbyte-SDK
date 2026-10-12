from __future__ import annotations

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


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
        # Read the recursive flag strictly, require write permission, verify the path exists, delete it, and return the path.
        path = call.arguments.get("path", "")
        try:
            recursive = self._resolve_bool_argument(call, "recursive", default=False)
            self._require_write()
            target = self._path(path)
            # @intent delete-keeps-the-configured-root
            # The scoped path may name the root itself (".", ""), which is fine for
            # reading but would wipe the whole workspace here, so it is refused.
            if target == self._config.resolved_root():
                return ToolResult.error(self.name, "The configured root itself cannot be deleted; delete the entries inside it instead.")
            if not target.exists():
                raise ToolExecutionError("Path does not exist.", details={"path": str(target)})
            self.backend.delete(target, recursive=recursive)
            return ToolResult.success(self.name, str(target), metadata={"path": str(target), "recursive": recursive})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "DeleteTool",
]
