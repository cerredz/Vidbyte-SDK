from __future__ import annotations

import dataclasses

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem import FileSystemPermissions, LineEndings
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ReadLinesTool(FileSystemTool):
    """Read a bounded line window from a scoped text file, returning newline-joined lines."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for reading a subset of lines from a text file.
        spec = ToolSpec(
            name="read_lines",
            description="Read a range of lines from a text file at the given path inside the configured root.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to read."),
                ToolParameter(name="start", type="integer", description="1-based line number to start from (inclusive).", required=False),
                ToolParameter(name="end", type="integer", description="1-based line number to end at (inclusive). Reads to EOF if omitted.", required=False),
            ),
            permission=ToolPermission.READ,
        )
        # Tell the model up front that a long range comes back in
        # windows, so it reads on from the line the footer names.
        limit = self._config.max_read_lines
        if limit is None:
            return spec
        return dataclasses.replace(spec, description=f"{spec.description} At most {limit:,} lines come back from one call; when more lines remain in the requested range, the result ends with a line naming the next start line.")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate range bounds, read and slice the lines, and return them
        # newline-joined, cut to the read window when one is set.
        path = call.arguments.get("path", "")
        start = int(self._optional_argument(call, "start", default=1))
        end_raw = call.arguments.get("end", None)
        end: int | None = int(end_raw) if end_raw is not None else None
        try:
            if start < 1:
                raise ToolExecutionError("ReadLinesTool start must be at least 1.")
            if end is not None and end < start:
                raise ToolExecutionError("ReadLinesTool end must be greater than or equal to start.")
            target = self._path(path)
            FileSystemPermissions.require_existing_file(target)
            # @intent read-lines-numbers-lines-as-on-disk
            # Split at "\n" only, like the edit diffs and grep -n, so a form feed
            # or U+2028 inside a line does not shift every later line number.
            lines = LineEndings.split_bare_lines(self.backend.read_text(target, encoding=self._config.encoding))
            selected = lines[start - 1 : end]
            metadata = {"path": str(target), "start": start, "end": end}
            # Without a window the whole requested range comes back.
            limit = self._config.max_read_lines
            if limit is None:
                return ToolResult.success(self.name, "\n".join(selected), metadata=metadata)
            # @intent one-read-returns-at-most-one-window
            # One read of a long file floods the history the model
            # re-sends on every call, so a range longer than the window
            # is cut, and a footer names the line to read on from.
            truncated = len(selected) > limit
            next_start = start + limit if truncated else None
            text = "\n".join(selected[:limit])
            if truncated:
                text = f"{text}\n[lines {start}-{start + limit - 1} of {len(lines)} shown; read on with start={next_start}]"
            return ToolResult.success(self.name, text, metadata={**metadata, "truncated": truncated, "total_lines": len(lines), "next_start": next_start})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "ReadLinesTool",
]
