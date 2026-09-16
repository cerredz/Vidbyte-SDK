"""FILE: vidbyte/tools/integrations/github/base.py

PURPOSE: Owns shared scope and result behavior for repository-scoped GitHub tools.
ROLE IN CODEBASE: Concrete list, read, and search tools inherit these class-bound validators.
ARCHITECTURE NOTE: Owner/repo are closed over from SourceConfig; model arguments contain only operation values.
COMMON MODIFICATION PATTERNS: Add shared validation here only when every GitHub tool needs the same rule.
KNOWN EDGE CASES: Empty paths are valid only for directory listing, and tool failures become safe failed results.
RELATED DOCS: docs/design/source-context-tools.md and vidbyte/tools/integrations/github/README.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from typing import Any

from vidbyte.integrations.github import GitHubClient
from vidbyte.lib.constants.integrations import (
    SOURCES_MAX_CONTROL_CODE,
    SOURCES_MAX_PATH_CHARS,
    SOURCES_MAX_QUERY_CHARS,
    SOURCES_MAX_REF_CHARS,
)
from vidbyte.lib.dataclasses.integrations import SourceConfig
from vidbyte.lib.dataclasses.tools import ToolCall, ToolParameter, ToolResult, ToolSpec
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.text import TextClipper
from vidbyte.tools.base import BaseTool

_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/-]{1,64}$")


class GitHubToolBase(BaseTool):
    """Provides construction-bound scope and common input/result helpers."""

    operation = "github"

    def __init__(self, client: GitHubClient, config: SourceConfig, max_output_bytes: int) -> None:
        """Close over the selected client, repository, and output ceiling."""
        self._client = client
        self._config = config
        self._max_output_bytes = max_output_bytes

    def spec(self) -> ToolSpec:
        """Require each concrete tool to declare its own model-facing contract."""
        raise NotImplementedError

    async def execute(self, call: ToolCall) -> ToolResult:
        """Require each concrete tool to implement its provider operation."""
        raise NotImplementedError

    def _arguments(self, call: ToolCall) -> dict[str, Any]:
        """Normalize call arguments into a plain mapping for class-bound validation."""
        return dict(call.arguments) if isinstance(call.arguments, Mapping) else {}

    def _path(self, raw: Any, *, allow_empty: bool) -> str:
        """Validate and normalize one repository-relative path without widening scope."""
        if allow_empty and (raw is None or (isinstance(raw, str) and not raw.strip())):
            return ""
        if not isinstance(raw, str) or not raw.strip() or len(raw) > SOURCES_MAX_PATH_CHARS:
            raise ConfigurationError("Tool 'path' must be a nonempty string within the length limit.")
        value = raw.strip()
        lowered = value.lower()
        if any(ord(char) <= SOURCES_MAX_CONTROL_CODE for char in value) or "://" in lowered or lowered.startswith(("http:", "https:", "git@", "/", "//")) or re.match(r"^[a-z]:/", lowered):
            raise ConfigurationError("Tool 'path' must be repo-relative, never a URL or absolute path.")
        normalized = posixpath.normpath(value.replace("\\", "/")).lstrip("/")
        if normalized in ("", ".") or normalized.startswith("..") or "/../" in f"/{normalized}/":
            raise ConfigurationError("Tool 'path' must stay inside the bound repository.")
        return normalized

    def _ref(self, raw: Any) -> str | None:
        """Validate an optional branch or commit ref without allowing route syntax."""
        if raw is None or raw == "":
            return None
        if not isinstance(raw, str) or len(raw) > SOURCES_MAX_REF_CHARS or not _REF_PATTERN.fullmatch(raw) or any(ord(char) <= SOURCES_MAX_CONTROL_CODE for char in raw):
            raise ConfigurationError("Tool 'ref' must use safe branch or commit characters within the length limit.")
        return raw

    def _query(self, raw: Any) -> str:
        """Validate search text and reject repository qualifiers that widen scope."""
        if not isinstance(raw, str) or not raw.strip() or len(raw) > SOURCES_MAX_QUERY_CHARS or any(ord(char) <= SOURCES_MAX_CONTROL_CODE for char in raw):
            raise ConfigurationError("Tool 'query' must be a nonempty string within the length limit.")
        value = raw.strip()
        if "repo:" in value.lower():
            raise ConfigurationError("Tool 'query' must not name a repository; search stays in the bound repo.")
        return value

    # @intent provider-boundary
    def _success(self, name: str, payload: Any) -> ToolResult:
        """Clip a provider payload and stamp safe scope and transport metadata."""
        text = payload if isinstance(payload, str) else str(getattr(payload, "body", ""))
        transport = str(getattr(payload, "transport", "unknown"))
        clipped = TextClipper.clip(text, self._max_output_bytes)
        return ToolResult.success(
            name,
            clipped,
            metadata={**self._provenance(), "transport": transport, "truncated": clipped != text},
        )

    def _failure(self, name: str, exc: Exception, *, validation: bool = False) -> ToolResult:
        """Return a failed result with only a safe category, never provider output."""
        return ToolResult.failure(
            name,
            "The tool arguments are invalid." if validation else "The provider request failed.",
            metadata={**self._provenance(), "error_type": "validation" if validation else type(exc).__name__},
        )

    # @intent provider-boundary
    def _provenance(self) -> dict[str, str]:
        """Stamp result identity from the construction-bound provider scope."""
        return {"provider": self._config.provider.value, "resource": f"{self._config.owner}/{self._config.repo}", "operation": self.operation}

    @staticmethod
    def _parameter(name: str, description: str, *, required: bool, default: Any = None) -> ToolParameter:
        """Build one immutable model parameter declaration for concrete tool specs."""
        return ToolParameter(name=name, type="string", description=description, required=required, default=default)


__all__ = ["GitHubToolBase"]
