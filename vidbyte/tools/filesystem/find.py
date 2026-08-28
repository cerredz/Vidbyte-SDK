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


class FindTool(FileSystemTool):
    """Find files or directories matching a glob pattern under a scoped root directory."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for glob-pattern file search.
        return ToolSpec(
            name="find",
            description="Find files or directories matching a glob pattern under a root directory inside the configured root.",
            parameters=(
                ToolParameter(name="pattern", type="string", description="Glob pattern to match (e.g. '*.py')."),
                ToolParameter(name="root", type="string", description="Relative path of the directory to search under.", required=False),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate the root directory exists, run the glob search, and return newline-joined matches.
        pattern = call.arguments.get("pattern", "")
        root = call.arguments.get("root", ".")
        try:
            target_root = self._path(root)
            FileSystemPermissions.require_existing_directory(target_root)
            matches = self.backend.find(target_root, pattern)
            return ToolResult.success(self.name, "\n".join(matches), metadata={"root": str(target_root), "pattern": pattern})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "FindTool",
]
