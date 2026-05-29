from __future__ import annotations

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ReadLinesTool(FileSystemTool):
    """Read a bounded line window from a scoped text file, returning newline-joined lines."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for reading a subset of lines from a text file.
        return ToolSpec(
            name="read_lines",
            description="Read a range of lines from a text file at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to read."),
                ToolParameter(name="start", type="integer", description="1-based line number to start from (inclusive).", required=False),
                ToolParameter(name="end", type="integer", description="1-based line number to end at (inclusive). Reads to EOF if omitted.", required=False),
            ),
            permission=ToolPermission.READ,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate range bounds, read and slice the lines, return them newline-joined.
        path = call.arguments.get("path", "")
        start = int(call.arguments.get("start", 1))
        end_raw = call.arguments.get("end", None)
        end: int | None = int(end_raw) if end_raw is not None else None
        try:
            if start < 1:
                raise ToolExecutionError("ReadLinesTool start must be at least 1.")
            if end is not None and end < start:
                raise ToolExecutionError("ReadLinesTool end must be greater than or equal to start.")
            target = self._path(path)
            FileSystemPermissions.require_existing_file(target)
            lines = self.backend.read_text(target, encoding=self._config.encoding).splitlines()
            selected = lines[start - 1 : end]
            return ToolResult.success(self.name, "\n".join(selected), metadata={"path": str(target), "start": start, "end": end})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "ReadLinesTool",
]
