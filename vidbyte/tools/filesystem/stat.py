from __future__ import annotations

import dataclasses
import json

from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class StatTool(FileSystemTool):
    """Return portable metadata for a scoped path as a JSON-serialized object."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for reading file/directory metadata.
        return ToolSpec(
            name="stat",
            description="Return metadata (exists, is_file, is_dir, size, modified_time) for a path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to inspect."),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Resolve the path, call stat on the backend, and return the metadata as JSON.
        path = call.arguments.get("path", "")
        try:
            target = self._path(path)
            file_stat = self.backend.stat(target)
            output = json.dumps(dataclasses.asdict(file_stat))
            return ToolResult.success(self.name, output, metadata={"path": str(target)})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "StatTool",
]
