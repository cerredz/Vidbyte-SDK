from __future__ import annotations

from vidbyte.lib.tools.filesystem import LineEndings
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class AppendTool(FileSystemTool):
    """Append text to a scoped file, creating parent directories if requested."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for appending text to files.
        return ToolSpec(
            name="append_text",
            description="Append text content to an existing or new file at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to append to."),
                ToolParameter(name="content", type="string", description="Text content to append."),
                ToolParameter(name="create_parents", type="boolean", description="Create parent directories if they do not exist.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Extract arguments (the create_parents flag strictly), append to the file, and return the resolved path on success.
        path = call.arguments.get("path", "")
        content = call.arguments.get("content", "")
        try:
            create_parents = self._resolve_bool_argument(call, "create_parents", default=False)
            self._require_write()
            target = self._path(path)
            # @intent append-keeps-file-line-endings
            # Append in the existing file's own line endings so it never ends up mixed; a new file keeps the platform default.
            # Bytes the encoding cannot read are replaced only for this check, so detection never makes the append fail.
            newline = LineEndings.detect(self.backend.read_binary(target).decode(self._config.encoding, errors="replace")) if target.is_file() else None
            self.backend.append_text(target, content, encoding=self._config.encoding, create_parents=create_parents, newline=newline)
            return ToolResult.success(self.name, str(target), metadata={"path": str(target), "encoding": self._config.encoding})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "AppendTool",
]
