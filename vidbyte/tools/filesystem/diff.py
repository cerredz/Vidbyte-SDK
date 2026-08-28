from __future__ import annotations

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class DiffTool(FileSystemTool):
    """Create a unified diff between a scoped file and proposed content or another scoped file."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for generating a unified diff.
        return ToolSpec(
            name="diff",
            description="Generate a unified diff for a file at the given path. Provide either content or other_path to compare against.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to the base file."),
                ToolParameter(name="content", type="string", description="Proposed text to diff against the file.", required=False),
                ToolParameter(name="other_path", type="string", description="Relative path to a second file to diff against.", required=False),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Read the base file and diff it against either inline content or a second file.
        path = call.arguments.get("path", "")
        content: str | None = call.arguments.get("content", None)
        other_path: str | None = call.arguments.get("other_path", None)
        try:
            target = self._path(path)
            FileSystemPermissions.require_existing_file(target)
            if content is None and other_path is None:
                raise ToolExecutionError("DiffTool requires content or other_path.")
            if other_path is not None:
                other = self._path(other_path)
                FileSystemPermissions.require_existing_file(other)
                content = self.backend.read_text(other, encoding=self._config.encoding)
                label = str(other)
            else:
                label = "proposed"
            diff = self.backend.diff_text(target, content or "", encoding=self._config.encoding, label=label)
            return ToolResult.success(self.name, diff, metadata={"path": str(target), "other_path": other_path})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "DiffTool",
]
