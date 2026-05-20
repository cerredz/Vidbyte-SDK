from __future__ import annotations

from pathlib import Path

from vidbyte.lib.dataclasses import ToolResult
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class ZipTool(FileSystemTool):
    """Create a zip archive from a scoped file or directory."""

    def run(self, source: str, destination: str) -> ToolResult:
        self._require_write()
        source_path = self._path(source)
        destination_path = self._path(destination)
        if source_path.is_dir():
            FileSystemPermissions.require_existing_directory(source_path)
        else:
            FileSystemPermissions.require_existing_file(source_path)
        self.backend.zip_path(source_path, destination_path)
        return ToolResult(value=Path(destination_path), metadata={"source": str(source_path), "destination": str(destination_path)})


class UnzipTool(FileSystemTool):
    """Extract a zip archive into a scoped directory."""

    def run(self, source: str, destination: str) -> ToolResult:
        self._require_write()
        source_path = self._path(source)
        destination_path = self._path(destination)
        FileSystemPermissions.require_existing_file(source_path)
        extracted = self.backend.unzip_path(source_path, destination_path)
        return ToolResult(value=extracted, metadata={"source": str(source_path), "destination": str(destination_path)})


__all__ = [
    "UnzipTool",
    "ZipTool",
]
