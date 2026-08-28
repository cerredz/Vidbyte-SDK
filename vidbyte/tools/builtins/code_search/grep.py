"""Context Protocol Header

Description:
    Implements literal and regex grep over root-scoped source files.
Purpose:
    Gives agents line-numbered, context-bounded search results without exposing
    full files or unsafe paths.
Architecture:
    - GrepTool: Built-in read-only text search tool.
Relations:
    Related to vidbyte.tools.builtins.code_search.base and semantic.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from vidbyte.tools.builtins.code_search.base import BaseCodeSearchTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class GrepTool(BaseCodeSearchTool):
    """Search text files for literal or regex matches."""

    def spec(self) -> ToolSpec:
        """Return the model-facing grep tool declaration."""
        return ToolSpec(
            name="grep",
            description="Search files for a literal string or regular expression.",
            permission=ToolPermission.READ,
            parameters=(
                ToolParameter("pattern", "string", "Literal string or regex pattern to search."),
                ToolParameter("subdir", "string", "Subdirectory to search from.", required=False),
                ToolParameter("regex", "boolean", "Whether pattern is regex.", required=False),
                ToolParameter("extensions", "array", "File extensions to include.", required=False),
                ToolParameter("context_lines", "integer", "Lines before and after each match.", required=False),
                ToolParameter("max_results", "integer", "Maximum matches to return.", required=False),
                ToolParameter("max_chars", "integer", "Maximum output characters.", required=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run grep and return line-numbered snippets."""
        pattern = str(call.arguments["pattern"])
        subdir = str(call.arguments.get("subdir", "."))
        use_regex = bool(call.arguments.get("regex", False))
        extensions = self._extensions(call.arguments.get("extensions", ()))
        context_lines = max(0, min(int(call.arguments.get("context_lines", 2)), 5))
        max_results = max(1, min(int(call.arguments.get("max_results", 50)), 500))
        max_chars = max(200, min(int(call.arguments.get("max_chars", 12000)), 50000))
        try:
            compiled = re.compile(pattern if use_regex else re.escape(pattern))
            files = tuple(self.iter_files(subdir, extensions=extensions))
        except re.error as exc:
            return ToolResult.error(self.name, f"Invalid regex: {exc}", metadata={"error": "bad_regex"})
        except ValueError as exc:
            return ToolResult.error(self.name, str(exc), metadata={"error": "unsafe_path"})

        snippets: list[str] = []
        for path in files:
            lines = self.read_text_lines(path)
            for index, line in enumerate(lines):
                if not compiled.search(line):
                    continue
                start = max(0, index - context_lines)
                end = min(len(lines), index + context_lines + 1)
                rel = self.relative_path(path)
                body = "\n".join(
                    f"{line_number + 1}: {lines[line_number]}"
                    for line_number in range(start, end)
                )
                snippets.append(f"{rel}:{index + 1}\n{body}")
                if len(snippets) >= max_results:
                    output = "\n\n".join(snippets) + "\n\nResults truncated; narrow the pattern."
                    if len(output) > max_chars:
                        output = output[:max_chars] + "\n...[truncated]"
                    return ToolResult.success(
                        self.name,
                        output,
                        metadata={"count": len(snippets), "truncated": True},
                    )
        if not snippets:
            return ToolResult.success(self.name, "No matches found.", metadata={"count": 0})
        return ToolResult.success(
            self.name,
            self._bounded_output("\n\n".join(snippets), max_chars),
            metadata={"count": len(snippets), "truncated": len("\n\n".join(snippets)) > max_chars},
        )

    def _extensions(self, value: object) -> Sequence[str]:
        """Normalize extension arguments from strings or sequences."""
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        if isinstance(value, Sequence):
            return tuple(str(part) for part in value)
        return ()

    def _bounded_output(self, output: str, max_chars: int) -> str:
        """Truncate grep output to the requested character budget."""
        if len(output) <= max_chars:
            return output
        return output[:max_chars] + "\n...[truncated]"
