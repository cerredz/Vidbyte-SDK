"""FILE: vidbyte/tools/integrations/github/list_files.py

PURPOSE: Defines the repository-scoped GitHub directory listing tool.
ROLE IN CODEBASE: Exposes one model-facing read operation composed by SourceTool.
ARCHITECTURE NOTE: The repository scope is inherited from GitHubToolBase and cannot be supplied by the model.
COMMON MODIFICATION PATTERNS: Change only this tool's spec or list call; keep shared validation in base.py.
KNOWN EDGE CASES: An empty path deliberately lists the repository root.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

from vidbyte.lib.constants.integrations import SOURCES_MAX_DIRECTORY_ENTRIES
from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission, ToolResult, ToolSpec
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    SourceFetchError,
)
from vidbyte.tools.integrations.github.base import GitHubToolBase


class GitHubListFilesTool(GitHubToolBase):
    """Lists names directly inside one bound repository directory."""

    operation = "list_files"

    def spec(self) -> ToolSpec:
        """Declare the root-or-directory listing contract."""
        return ToolSpec(
            name="github_list_files",
            description="List files and directories directly inside a path in the repository fixed when this tool was built. Use an empty path for the repository root. Results are names only and are bounded in count. An optional branch or commit ref may be supplied.",
            parameters=(
                self._parameter("path", "Repo-relative directory; empty selects the repository root.", required=False, default=""),
                self._parameter("ref", "Optional safe branch or commit ref.", required=False),
            ),
            permission=ToolPermission.SAFE,
            metadata={"source": "integrations", "provider": "github", "operation": self.operation},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate a directory and list it through the bound GitHub client."""
        args = self._arguments(call)
        try:
            path = self._path(args.get("path", ""), allow_empty=True)
            payload = await self._client.list_repo_files(self._config, path, self._ref(args.get("ref")), max_entries=SOURCES_MAX_DIRECTORY_ENTRIES)
        except ConfigurationError as exc:
            return self._failure("github_list_files", exc, validation=True)
        except (ProviderRequestError, SourceFetchError, TimeoutError, OSError, ValueError, TypeError) as exc:
            return self._failure("github_list_files", exc)
        return self._success("github_list_files", payload)

    def validate_call(self, call: ToolCall) -> str | None:
        """Reject invalid directory arguments before the tool executor runs."""
        base_error = super().validate_call(call)
        if base_error is not None:
            return base_error
        try:
            args = self._arguments(call)
            self._path(args.get("path", ""), allow_empty=True)
            self._ref(args.get("ref"))
        except ConfigurationError:
            return "The tool arguments are invalid."
        return None


__all__ = ["GitHubListFilesTool"]
