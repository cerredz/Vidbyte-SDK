from __future__ import annotations

import dataclasses
from pathlib import Path

from vidbyte.lib.tools.filesystem.newlines import LineEndings
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class WriteTextTool(FileSystemTool):
    """Write text content to a scoped file, creating parent directories if requested."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for writing text files.
        spec = ToolSpec(
            name="write_text",
            description="Write text content to a file at the given path inside the configured root. The result shows a diff of the change, or the line count of a new file.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to write."),
                ToolParameter(name="content", type="string", description="Text content to write."),
                ToolParameter(name="create_parents", type="boolean", description="Create parent directories if they do not exist.", required=False),
            ),
            permission=ToolPermission.WRITE,
        )
        # Tell the model up front that big existing files are edited
        # with replace_text, so it does not try a whole rewrite first.
        limit = self._config.max_overwrite_lines
        if limit is None:
            return spec
        return dataclasses.replace(spec, description=f"{spec.description} Existing files over {limit:,} lines cannot be replaced whole; change them with replace_text.")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Extract arguments (the create_parents flag strictly), write the file, and return the resolved path on success.
        path = call.arguments.get("path", "")
        content = call.arguments.get("content", "")
        try:
            create_parents = self._resolve_bool_argument(call, "create_parents", default=False)
            self._require_write()
            target = self._path(path)
            # @intent big-existing-files-are-edited-not-rewritten
            # A model that rewrites a long file from memory often drops
            # code without noticing, so an existing file over the line
            # limit is refused untouched and the model is sent to
            # replace_text instead.
            refusal = self._overwrite_refusal(path, target)
            if refusal is not None:
                return ToolResult.error(self.name, refusal)
            # Describe the change while the old file is still on disk. A
            # new file gets its line count, not a diff that repeats it.
            exists = self.backend.stat(target).is_file
            # @intent model-crlf-text-keeps-file-endings
            # An existing file is written in its own endings below, so CRLF the model spelled is first made LF, to land once.
            content = LineEndings.to_lf(content) if exists else content
            change = self._edit_diff(target, content) if exists else f"created, {len(LineEndings.split_lines(content))} lines"
            # @intent write-keeps-file-line-endings
            # Replace an existing file in its own line endings so the rewrite
            # does not flip every line; a new file keeps the platform default.
            # Bytes the encoding cannot read are replaced only for this check,
            # so a file that is not valid text can still be overwritten.
            newline = LineEndings.detect(self.backend.read_binary(target).decode(self._config.encoding, errors="replace")) if exists else None
            self.backend.write_text(target, content, encoding=self._config.encoding, create_parents=create_parents, newline=newline)
            # Show the model the path, then what its write changed.
            return ToolResult.success(self.name, f"{target}\n{change}", metadata={"path": str(target), "encoding": self._config.encoding})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))

    def _overwrite_refusal(self, path: str, target: Path) -> str | None:
        """Return the refusal text when target is an existing file over max_overwrite_lines, else None."""
        limit = self._config.max_overwrite_lines
        if limit is None or not self.backend.stat(target).is_file:
            return None
        # Count lines from bytes, so an undecodable file cannot break
        # the check, and a last line without a newline still counts.
        data = self.backend.read_binary(target)
        lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        if lines <= limit:
            return None
        return f"write_text refused: {path} already has {lines:,} lines, over the {limit:,}-line limit for replacing a whole existing file. Use replace_text to change only the parts that need to change."
