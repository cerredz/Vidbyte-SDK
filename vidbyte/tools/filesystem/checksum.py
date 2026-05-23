from __future__ import annotations

import hashlib

from vidbyte.lib.dataclasses.tool_types import ToolResult
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool


class ChecksumTool(FileSystemTool):
    """Compute a SHA-256 checksum for a scoped file."""

    def run(self, path: str) -> ToolResult:
        target = self._path(path)
        FileSystemPermissions.require_existing_file(target)
        digest = hashlib.sha256(self.backend.read_binary(target)).hexdigest()
        return ToolResult(value=digest, metadata={"path": str(target), "algorithm": "sha256"})


__all__ = [
    "ChecksumTool",
]
