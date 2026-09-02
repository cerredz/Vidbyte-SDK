from __future__ import annotations

import hashlib

from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ChecksumTool(FileSystemTool):
    """Compute a SHA-256 checksum for a scoped file and return the hex digest."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for checksumming a file.
        return ToolSpec(
            name="checksum",
            description="Compute the SHA-256 checksum of a file at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to the file."),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Resolve the path, read its bytes, compute SHA-256, and return the hex digest.
        path = call.arguments.get("path", "")
        try:
            target = self._path(path)
            FileSystemPermissions.require_existing_file(target)
            digest = hashlib.sha256(self.backend.read_binary(target)).hexdigest()
            return ToolResult.success(self.name, digest, metadata={"path": str(target), "algorithm": "sha256"})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "ChecksumTool",
]
