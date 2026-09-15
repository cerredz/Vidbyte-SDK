"""FILE: vidbyte/tools/integrations/github/read_file.py

PURPOSE: Defines the repository-scoped GitHub file reader tool.
ROLE IN CODEBASE: Exposes one model-facing read operation composed by SourceTool.
ARCHITECTURE NOTE: The repository scope is inherited from GitHubToolBase and file paths are validated before requests.
COMMON MODIFICATION PATTERNS: Change only this tool's spec or read call; keep shared validation in base.py.
KNOWN EDGE CASES: Empty paths are rejected because the operation requires a file, not a directory.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission, ToolResult, ToolSpec
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    SourceFetchError,
)
from vidbyte.tools.integrations.github.base import GitHubToolBase


class GitHubReadFileTool(GitHubToolBase):
    """Reads decoded text from one file inside the bound repository."""

    operation = "read_file"

    def spec(self) -> ToolSpec:
        """Declare the required file path and optional ref contract."""
        return ToolSpec(
            name="github_read_file",
            description="Read decoded text from one file inside the repository fixed when this tool was built. Supply only a repo-relative file path and, optionally, a safe branch or commit ref. Output is clipped to the configured byte ceiling with an explicit marker when necessary. Paths outside the repository are rejected before any request.",
            parameters=(
                self._parameter("path", "Repo-relative file path inside the bound repository.", required=True),
                self._parameter("ref", "Optional safe branch or commit ref.", required=False),
            ),
            permission=ToolPermission.SAFE,
            metadata={"source": "integrations", "provider": "github", "operation": self.operation},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate a file path and read it through the bound GitHub client."""
        args = self._arguments(call)
        try:
            path = self._path(args.get("path"), allow_empty=False)
            payload = await self._client.read_repo_file(self._config, path, self._ref(args.get("ref")), max_bytes=self._max_output_bytes)
        except ConfigurationError as exc:
            return self._failure("github_read_file", exc, validation=True)
        except (ProviderRequestError, SourceFetchError, TimeoutError, OSError, ValueError, TypeError) as exc:
            return self._failure("github_read_file", exc)
        return self._success("github_read_file", payload)

    def validate_call(self, call: ToolCall) -> str | None:
        """Reject invalid file arguments before the tool executor runs."""
        base_error = super().validate_call(call)
        if base_error is not None:
            return base_error
        try:
            args = self._arguments(call)
            self._path(args.get("path"), allow_empty=False)
            self._ref(args.get("ref"))
        except ConfigurationError:
            return "The tool arguments are invalid."
        return None


__all__ = ["GitHubReadFileTool"]
