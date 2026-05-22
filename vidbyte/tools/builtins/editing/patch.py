"""Context Protocol Header

Description:
    Implements exact block replacement for root-scoped text files.
Purpose:
    Gives agents a surgical edit primitive that refuses missing or ambiguous
    matches and returns an auditable unified diff.
Architecture:
    - PatchTool: WRITE-permission tool for exact search/replace patches.
Relations:
    Related to vidbyte.tools.security.permissions and code search tools.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class PatchTool(BaseTool):
    """Apply exact search/replace patches inside a configured root."""

    def __init__(self, root_dir: str | Path, *, encoding: str = "utf-8") -> None:
        """Store the safe root and text encoding."""
        self.root_dir = Path(root_dir).resolve()
        self.encoding = encoding

    def spec(self) -> ToolSpec:
        """Return the model-facing patch tool declaration."""
        return ToolSpec(
            name="patch_file",
            description="Replace one exact block in a text file and return a unified diff.",
            permission=ToolPermission.WRITE,
            parameters=(
                ToolParameter("file_path", "string", "Path to a file under the configured root."),
                ToolParameter("search_block", "string", "Exact text block to replace."),
                ToolParameter("replace_block", "string", "Replacement text block."),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Apply the patch only when the search block occurs exactly once."""
        file_path = str(call.arguments["file_path"])
        search_block = str(call.arguments["search_block"])
        replace_block = str(call.arguments["replace_block"])
        if not search_block:
            return ToolResult.error(self.name, "search_block cannot be empty.", metadata={"error": "empty_search"})
        try:
            path = self._resolve(file_path)
            before = path.read_text(encoding=self.encoding)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            return ToolResult.error(self.name, str(exc), metadata={"error": "read_error"})

        count = before.count(search_block)
        if count == 0:
            return ToolResult.error(
                self.name,
                "Code block not found. Ensure spacing and indentation match exactly.",
                metadata={"error": "not_found"},
            )
        if count > 1:
            return ToolResult.error(
                self.name,
                "Ambiguous patch. The search block matches multiple locations.",
                metadata={"error": "ambiguous", "matches": count},
            )

        after = before.replace(search_block, replace_block, 1)
        try:
            path.write_text(after, encoding=self.encoding)
        except OSError as exc:
            return ToolResult.error(self.name, str(exc), metadata={"error": "write_error"})
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )
        )
        return ToolResult.success(
            self.name,
            diff or "Patch applied with no line-level diff.",
            metadata={"changed": True, "file_path": file_path},
        )

    def _resolve(self, file_path: str) -> Path:
        """Resolve a file path under root and reject traversal outside it."""
        path = (self.root_dir / file_path).resolve()
        try:
            path.relative_to(self.root_dir)
        except ValueError as exc:
            raise ValueError(f"Path escapes root: {file_path}") from exc
        if not path.is_file():
            raise ValueError(f"File not found: {file_path}")
        return path
