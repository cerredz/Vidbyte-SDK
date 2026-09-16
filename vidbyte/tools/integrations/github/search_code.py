"""FILE: vidbyte/tools/integrations/github/search_code.py

PURPOSE: Defines the repository-scoped GitHub code search tool.
ROLE IN CODEBASE: Exposes one model-facing search operation composed by SourceTool.
ARCHITECTURE NOTE: The repository qualifier is provider-authored and user-supplied qualifiers are rejected.
COMMON MODIFICATION PATTERNS: Change only this tool's spec or search call; keep shared validation in base.py.
KNOWN EDGE CASES: Empty and cross-repository queries fail before any transport request.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

from vidbyte.lib.constants.integrations import SOURCES_MAX_SEARCH_ITEMS
from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission, ToolResult, ToolSpec
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    SourceFetchError,
)
from vidbyte.tools.integrations.github.base import GitHubToolBase


class GitHubSearchCodeTool(GitHubToolBase):
    """Searches code within one repository fixed at construction time."""

    operation = "search_code"

    def spec(self) -> ToolSpec:
        """Declare the required query and optional ref contract."""
        return ToolSpec(
            name="github_search_code",
            description="Search code text within the repository fixed when this tool was built. Supply a query and, optionally, a safe branch or commit ref. Repository qualifiers are rejected because the provider adds the bound repository itself. Results are matching paths bounded in count.",
            parameters=(
                self._parameter("query", "Code text to search within the bound repository.", required=True),
                self._parameter("ref", "Optional safe branch or commit ref.", required=False),
            ),
            permission=ToolPermission.SAFE,
            metadata={"source": "integrations", "provider": "github", "operation": self.operation},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate search text and run it through the bound GitHub client."""
        args = self._arguments(call)
        try:
            payload = await self._client.search_repo_code(self._config, self._query(args.get("query")), self._ref(args.get("ref")), max_items=SOURCES_MAX_SEARCH_ITEMS)
        except ConfigurationError as exc:
            return self._failure("github_search_code", exc, validation=True)
        except (ProviderRequestError, SourceFetchError, TimeoutError, OSError, ValueError, TypeError) as exc:
            return self._failure("github_search_code", exc)
        return self._success("github_search_code", payload)

    def validate_call(self, call: ToolCall) -> str | None:
        """Reject invalid search arguments before the tool executor runs."""
        base_error = super().validate_call(call)
        if base_error is not None:
            return base_error
        try:
            args = self._arguments(call)
            self._query(args.get("query"))
            self._ref(args.get("ref"))
        except ConfigurationError:
            return "The tool arguments are invalid."
        return None


__all__ = ["GitHubSearchCodeTool"]
