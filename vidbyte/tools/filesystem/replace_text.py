from __future__ import annotations

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem import FileSystemPermissions, LineEndings
from vidbyte.lib.util import SubstringCounter
from vidbyte.tools.filesystem._base_tool import FileSystemTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ReplaceTextTool(FileSystemTool):
    """Replace the single occurrence of a search string in a scoped text file."""

    def spec(self) -> ToolSpec:
        # Declares the model-facing contract for exact-once in-place text replacement.
        return ToolSpec(
            name="replace_text",
            description="Replace a search string that appears exactly once in a file at the given path inside the configured root. The result shows a diff of the change.",
            parameters=(
                ToolParameter(name="path", type="string", description="Relative path to the file."),
                ToolParameter(name="search", type="string", description="Text to search for (must appear exactly once)."),
                ToolParameter(name="replacement", type="string", description="Text to replace the search string with."),
            ),
            permission=ToolPermission.WRITE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Read, validate uniqueness of the search string, replace it, and write back.
        path = call.arguments.get("path", "")
        search = call.arguments.get("search", "")
        replacement = call.arguments.get("replacement", "")
        try:
            self._require_write()
            if not search:
                raise ToolExecutionError("ReplaceTextTool search cannot be empty.")
            target = self._path(path)
            FileSystemPermissions.require_existing_file(target)
            content = self.backend.read_text(target, encoding=self._config.encoding)
            # Remember the file's own line endings so the edit does not rewrite every line.
            newline = LineEndings.detect(self.backend.read_binary(target).decode(self._config.encoding))
            # @intent model-crlf-text-keeps-file-endings
            # The file reads back as LF and is written in its own endings, so CRLF the model spelled is made LF to match and land once.
            search, replacement = LineEndings.to_lf(search), LineEndings.to_lf(replacement)
            # @intent unique-edit-counts-overlapping-matches
            count = SubstringCounter.count_overlapping(content, search)
            if count != 1:
                # Say which way the search failed, since the model only reads
                # this message: not found means re-read the file, while several
                # matches mean add surrounding text to pick one.
                reason = "it was not found" if count == 0 else f"it appears {count} times; include more surrounding text to make it unique"
                raise ToolExecutionError(
                    f"ReplaceTextTool requires the search text to appear exactly once, but {reason}.",
                    details={"matches": count, "path": str(target)},
                )
            updated = content.replace(search, replacement, 1)
            # Diff before writing, so the model sees which lines its
            # edit hit, and a failed write still returns only its error.
            change = self._edit_diff(target, updated)
            self.backend.write_text(target, updated, encoding=self._config.encoding, create_parents=False, newline=newline)
            return ToolResult.success(self.name, f"{target}\n{change}", metadata={"path": str(target), "replacements": 1})
        except Exception as exc:
            return ToolResult.error(self.name, str(exc))


__all__ = [
    "ReplaceTextTool",
]
