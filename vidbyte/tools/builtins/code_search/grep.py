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

import dataclasses
import re
from collections.abc import Sequence
from pathlib import Path

from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.builtins.code_search.base import CODE_SEARCH_MAX_FILE_BYTES, BaseCodeSearchTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

# The lines shown around each match when neither the call nor the tool
# sets them, and the most a call or the tool may ask for.
GREP_DEFAULT_CONTEXT_LINES = 2
GREP_MAX_CONTEXT_LINES = 5


class GrepTool(BaseCodeSearchTool):
    """Search text files for literal or regex matches."""

    def __init__(
        self,
        root_dir: str | Path,
        *,
        ignore_patterns: Sequence[str] | None = None,
        max_file_bytes: int = CODE_SEARCH_MAX_FILE_BYTES,
        smart_case: bool = False,
        context_lines: int = GREP_DEFAULT_CONTEXT_LINES,
    ) -> None:
        """Store the search root and safety settings, the letter-case rule, and the context lines a call gets when it sets none."""
        super().__init__(root_dir, ignore_patterns=ignore_patterns, max_file_bytes=max_file_bytes)
        self.smart_case = RecordFieldValidator.require_bool(smart_case, "GrepTool.smart_case")
        self.context_lines = RecordFieldValidator.require_int(context_lines, "GrepTool.context_lines", minimum=0, maximum=GREP_MAX_CONTEXT_LINES)

    def spec(self) -> ToolSpec:
        """Return the model-facing grep tool declaration."""
        spec = ToolSpec(
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
        # Tell the model each rule this tool was built with, so it does
        # not repeat a search in another letter case or ask for context
        # lines it already gets.
        added: list[str] = []
        if self.smart_case:
            added.append("A pattern with no uppercase letter matches without regard to letter case, and a pattern with one matches its case exactly.")
        if self.context_lines != GREP_DEFAULT_CONTEXT_LINES:
            added.append(f"When a call leaves context_lines out, it shows {self.context_lines} lines around each match.")
        if not added:
            return spec
        return dataclasses.replace(spec, description=" ".join((spec.description, *added)))

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run grep and return line-numbered snippets."""
        # Read the call's limits; a call that sets no context lines gets
        # the tool's own number.
        pattern = str(call.arguments["pattern"])
        subdir = str(self._optional_argument(call, "subdir", default="."))
        extensions = self._extensions(call.arguments.get("extensions", ()))
        context_lines = max(0, min(int(self._optional_argument(call, "context_lines", default=self.context_lines)), GREP_MAX_CONTEXT_LINES))
        max_results = max(1, min(int(self._optional_argument(call, "max_results", default=50)), 500))
        max_chars = max(200, min(int(self._optional_argument(call, "max_chars", default=12000)), 50000))
        try:
            # Compile the pattern, ignoring letter case when smart case
            # is on and the pattern holds no uppercase letter.
            use_regex = self._resolve_bool_argument(call, "regex", default=False)
            flags = re.IGNORECASE if self.smart_case and not self._has_uppercase(pattern, use_regex) else 0
            compiled = re.compile(pattern if use_regex else re.escape(pattern), flags)
            files = tuple(self.iter_files(subdir, extensions=extensions))
        except ToolExecutionError as exc:
            return ToolResult.error(self.name, str(exc), metadata={"error": "invalid_argument"})
        except re.error as exc:
            return ToolResult.error(self.name, f"Invalid regex: {exc}", metadata={"error": "bad_regex"})
        except ValueError as exc:
            return ToolResult.error(self.name, str(exc), metadata={"error": "unsafe_path"})

        # Collect one numbered snippet per matching line, stopping once
        # the result list is full.
        snippets: list[str] = []
        for path in files:
            lines = self.read_text_lines(path)
            for index, line in enumerate(lines):
                if not compiled.search(line):
                    continue
                # @intent code-search-truncation-means-hits-were-cut
                # Only a hit arriving after the list is already full proves results were cut.
                if len(snippets) >= max_results:
                    output = "\n\n".join(snippets) + "\n\nResults truncated; narrow the pattern."
                    if len(output) > max_chars:
                        output = output[:max_chars] + "\n...[truncated]"
                    return ToolResult.success(
                        self.name,
                        output,
                        metadata={"count": len(snippets), "truncated": True},
                    )
                start = max(0, index - context_lines)
                end = min(len(lines), index + context_lines + 1)
                rel = self.relative_path(path)
                body = "\n".join(
                    f"{line_number + 1}: {lines[line_number]}"
                    for line_number in range(start, end)
                )
                snippets.append(f"{rel}:{index + 1}\n{body}")
        # Return the snippets within the character budget.
        if not snippets:
            return ToolResult.success(self.name, "No matches found.", metadata={"count": 0})
        return ToolResult.success(
            self.name,
            self._bounded_output("\n\n".join(snippets), max_chars),
            metadata={"count": len(snippets), "truncated": len("\n\n".join(snippets)) > max_chars},
        )

    @staticmethod
    def _has_uppercase(pattern: str, use_regex: bool) -> bool:
        """Return whether the pattern holds an uppercase letter that smart case counts."""
        # @intent smart-case-skips-regex-escapes
        # In a regex, \S, \W, \D, \B, \A and \Z are escapes, not
        # capitals, so a letter right after an unescaped backslash is
        # dropped before the check; a literal pattern counts every letter.
        text = re.sub(r"\\.", "", pattern, flags=re.DOTALL) if use_regex else pattern
        return any(character.isupper() for character in text)

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
