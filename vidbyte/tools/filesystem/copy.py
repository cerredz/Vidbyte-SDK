from __future__ import annotations

from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class CopyTool(FileSystemTool):
    """Copy a scoped file or directory to another scoped destination."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for copying files or directories.
        return ToolSpec(
            name="copy",
            description="Copy a file or directory from source to destination inside the configured root.",
            parameters=(
                ToolParameter(name="source", type="string", description="Relative path to the source file or directory."),
                ToolParameter(name="destination", type="string", description="Relative path to the destination."),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate paths exist, copy the source to the destination, and return the destination path.
        source = call.arguments.get("source", "")
        destination = call.arguments.get("destination", "")
        try:
            self._require_write()
            source_path = self._path(source)
            destination_path = self._path(destination)
            if source_path.is_dir():
                FileSystemPermissions.require_existing_directory(source_path)
            else:
                FileSystemPermissions.require_existing_file(source_path)
            self.backend.copy(source_path, destination_path)
            return ToolResult.success(self.name, str(destination_path), metadata={"source": str(source_path), "destination": str(destination_path)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "CopyTool",
]
