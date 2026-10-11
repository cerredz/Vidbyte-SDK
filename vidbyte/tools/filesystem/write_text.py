from __future__ import annotations

from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class WriteTextTool(FileSystemTool):
    """Write text content to a scoped file, creating parent directories if requested."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for writing text files.
        return ToolSpec(
            name="write_text",
            description="Write text content to a file at the given path inside the configured root. The result shows a diff of the change, or the line count of a new file.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to write."),
                ToolParameter(name="content", type="string", description="Text content to write."),
                ToolParameter(name="create_parents", type="boolean", description="Create parent directories if they do not exist.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Extract arguments (the create_parents flag strictly), write the file, and return the resolved path on success.
        path = call.arguments.get("path", "")
        content = call.arguments.get("content", "")
        try:
            create_parents = self._resolve_bool_argument(call, "create_parents", default=False)
            self._require_write()
            target = self._path(path)
            # Describe the change while the old file is still on disk. A
            # new file gets its line count, not a diff that repeats it.
            change = self._edit_diff(target, content) if self.backend.stat(target).is_file else f"created, {len(content.splitlines())} lines"
            self.backend.write_text(target, content, encoding=self._config.encoding, create_parents=create_parents)
            # Show the model the path, then what its write changed.
            return ToolResult.success(self.name, f"{target}\n{change}", metadata={"path": str(target), "encoding": self._config.encoding})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))
