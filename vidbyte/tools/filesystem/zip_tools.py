from __future__ import annotations

from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class ZipTool(FileSystemTool):
    """Create a zip archive from a scoped file or directory."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for creating a zip archive.
        return ToolSpec(
            name="zip",
            description="Create a zip archive from a file or directory at source and write it to destination inside the configured root.",
            parameters=(
                ToolParameter(name="source", type="string", description="Relative path of the file or directory to archive."),
                ToolParameter(name="destination", type="string", description="Relative path for the output zip file."),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate the source exists, create the zip, and return the destination path.
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
            self.backend.zip_path(source_path, destination_path)
            return ToolResult.success(self.name, str(destination_path), metadata={"source": str(source_path), "destination": str(destination_path)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


class UnzipTool(FileSystemTool):
    """Extract a zip archive into a scoped destination directory."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for extracting a zip archive.
        return ToolSpec(
            name="unzip",
            description="Extract a zip archive at source into the destination directory inside the configured root.",
            parameters=(
                ToolParameter(name="source", type="string", description="Relative path of the zip file to extract."),
                ToolParameter(name="destination", type="string", description="Relative path of the directory to extract into."),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate the source zip exists, extract it, and return the list of extracted members.
        source = call.arguments.get("source", "")
        destination = call.arguments.get("destination", "")
        try:
            self._require_write()
            source_path = self._path(source)
            destination_path = self._path(destination)
            FileSystemPermissions.require_existing_file(source_path)
            extracted = self.backend.unzip_path(source_path, destination_path)
            return ToolResult.success(self.name, "\n".join(extracted), metadata={"source": str(source_path), "destination": str(destination_path)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "UnzipTool",
    "ZipTool",
]
