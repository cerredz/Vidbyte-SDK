"""Context Protocol Header

Description:
    Implements a root-scoped glob tool that returns matching paths.
Purpose:
    Lets agents discover files without reading file contents or dumping large
    directory trees into context.
Architecture:
    - GlobTool: Built-in read-only path matching tool.
Relations:
    Related to vidbyte.tools.builtins.code_search.base and grep.
"""

from __future__ import annotations

from pathlib import Path

from vidbyte.tools.builtins.code_search.base import BaseCodeSearchTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class GlobTool(BaseCodeSearchTool):
    """Find files by glob pattern under a configured root."""

    def spec(self) -> ToolSpec:
        """Return the model-facing glob tool declaration."""
        return ToolSpec(
            name="glob",
            description="Find files under a root directory using a glob pattern.",
            permission=ToolPermission.READ,
            parameters=(
                ToolParameter("pattern", "string", "Glob pattern such as '**/*.py'."),
                ToolParameter("subdir", "string", "Subdirectory to search from.", required=False),
                ToolParameter("max_results", "integer", "Maximum paths to return.", required=False),
                ToolParameter("max_chars", "integer", "Maximum output characters.", required=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run the glob search and return bounded relative paths."""
        pattern = str(call.arguments["pattern"])
        subdir = str(self._optional_argument(call, "subdir", default="."))
        max_results = max(1, min(int(self._optional_argument(call, "max_results", default=50)), 500))
        max_chars = max(200, min(int(self._optional_argument(call, "max_chars", default=10000)), 50000))
        try:
            start = self.resolve_under_root(subdir)
        except ValueError as exc:
            return ToolResult.error(self.name, str(exc), metadata={"error": "unsafe_path"})
        if not start.exists():
            return ToolResult.success(self.name, "No files matched.", metadata={"count": 0})

        matches: list[str] = []
        truncated = False
        for path in start.glob(pattern):
            resolved = Path(path).resolve()
            if not resolved.is_file() or self.should_ignore(resolved):
                continue
            try:
                relative = self.relative_path(resolved)
            except ValueError:
                continue
            # @intent code-search-truncation-means-hits-were-cut
            # Only a match arriving after the list is already full proves results were cut.
            if len(matches) >= max_results:
                truncated = True
                break
            matches.append(relative)
        if not matches:
            return ToolResult.success(self.name, "No files matched.", metadata={"count": 0})
        suffix = "\nResults truncated; narrow the pattern." if truncated else ""
        output = "\n".join(matches) + suffix
        if len(output) > max_chars:
            output = output[:max_chars] + "\n...[truncated]"
            truncated = True
        return ToolResult.success(
            self.name,
            output,
            metadata={"count": len(matches), "truncated": truncated},
        )
