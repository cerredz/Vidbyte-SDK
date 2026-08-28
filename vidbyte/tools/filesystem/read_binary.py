from __future__ import annotations

import base64

from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class ReadBinaryTool(FileSystemTool):
    """Read a binary file and return its content as a Base64-encoded string."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for reading binary files.
        return ToolSpec(
            name="read_binary",
            description="Read binary content from a file at the given path and return it Base64-encoded.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to read."),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Read raw bytes and encode as Base64 so the string output is safe for text channels.
        path = call.arguments.get("path", "")
        try:
            target = self._path(path)
            FileSystemPermissions.require_existing_file(target)
            data = self.backend.read_binary(target)
            encoded = base64.b64encode(data).decode("ascii")
            return ToolResult.success(self.name, encoded, metadata={"path": str(target), "encoding": "base64"})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "ReadBinaryTool",
]
