from __future__ import annotations

from pathlib import Path, PurePath

from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class MoveTool(FileSystemTool):
    """Move or rename a scoped file or directory to another scoped path."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for moving or renaming a file or directory.
        return ToolSpec(
            name="move",
            description="Move or rename a file or directory from source to destination inside the configured root.",
            parameters=(
                ToolParameter(name="source", type="string", description="Relative path of the source file or directory."),
                ToolParameter(name="destination", type="string", description="Relative path of the destination."),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate both paths, move the source to the destination, and return the destination path.
        source = call.arguments.get("source", "")
        destination = call.arguments.get("destination", "")
        try:
            self._require_write()
            source_path = self._path(source)
            destination_path = self._path(destination)
            # Keep the caller's spelling when the move only changes the letter case of the name.
            destination_path = self._case_only_destination(source_path, destination_path, destination)
            if source_path.is_dir():
                FileSystemPermissions.require_existing_directory(source_path)
            else:
                FileSystemPermissions.require_existing_file(source_path)
            self.backend.move(source_path, destination_path)
            return ToolResult.success(self.name, str(destination_path), metadata={"source": str(source_path), "destination": str(destination_path)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))

    @staticmethod
    def _case_only_destination(source_path: Path, destination_path: Path, destination: str) -> Path:
        # @intent move-keeps-requested-name-spelling
        # On a case-insensitive filesystem resolve() returns the on-disk spelling of an existing
        # entry, so "README.md" resolves back to "Readme.md" and the move silently does nothing.
        # When the destination resolved to the source itself and the requested name differs only
        # in case, rename to the requested spelling inside the same (already scope-checked) parent.
        requested_name = PurePath(destination).name
        if destination_path != source_path or requested_name == source_path.name:
            return destination_path
        if requested_name.casefold() != source_path.name.casefold():
            return destination_path
        return source_path.with_name(requested_name)


RenameTool = MoveTool


__all__ = [
    "MoveTool",
    "RenameTool",
]
