from __future__ import annotations

from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ListDirTool(FileSystemTool):
    """List files and subdirectories inside a scoped directory, returning newline-joined entries."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for listing a directory's contents.
        return ToolSpec(
            name="list_dir",
            description="List files and directories at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path of the directory to list.", required=False),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate the directory exists, list its entries, and return them as a newline-joined string.
        path = call.arguments.get("path", ".")
        try:
            target = self._path(path)
            FileSystemPermissions.require_existing_directory(target)
            entries = self.backend.list_dir(target)
            return ToolResult.success(self.name, "\n".join(entries), metadata={"path": str(target)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))
