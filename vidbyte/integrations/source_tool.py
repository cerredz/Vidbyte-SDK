"""FILE: vidbyte/integrations/source_tool.py

PURPOSE: Defines SourceTool, the public path building repository-scoped agent tools from one source dict.
ROLE IN CODEBASE: Builds ordinary BaseTool instances whose resource scope lives in construction closures, never in model arguments.
ARCHITECTURE NOTE: Scope enforcement holds where each tool builds its provider request, so forged arguments cannot widen access.
COMMON MODIFICATION PATTERNS: Add a repo operation as one more BaseTool subclass composed in build(), in deterministic order.
KNOWN EDGE CASES: Path escapes and repo: qualifiers fail before any request, and provider errors become failed results, never raises.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py and scripts/test-source-context-tools.py.
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from typing import Any

from vidbyte.integrations.github import clip_text
from vidbyte.integrations.providers import SourceProviderClient, create_client
from vidbyte.lib.constants.integrations import (
    SOURCES_DEFAULT_MAX_OUTPUT_BYTES,
    SOURCES_MAX_DIRECTORY_ENTRIES,
    SOURCES_MAX_PATH_CHARS,
    SOURCES_MAX_QUERY_CHARS,
    SOURCES_MAX_SEARCH_ITEMS,
)
from vidbyte.lib.dataclasses.integrations import SourceConfig, validate_ref
from vidbyte.lib.dataclasses.tools import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)
from vidbyte.lib.enums.integrations import SourceKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.base import BaseTool

_LIST_DESCRIPTION = (
    "github_list_files lists the names of files and directories directly inside one repository path. "
    "The repository is fixed when the tool is built, so the model only chooses a repo-relative directory and an optional branch. "
    "Results are names only, bounded in count, and stamped with the source they came from. "
    "Use it to discover layout before reading any file."
)
_READ_DESCRIPTION = (
    "github_read_file returns the decoded text of one file inside the bound repository. "
    "The repository is fixed when the tool is built, so the model only supplies a repo-relative path and an optional branch. "
    "Output is clipped to a byte ceiling with an explicit marker when the file is larger. "
    "Use it to inspect exactly the file the task needs and nothing outside the repository."
)
_SEARCH_DESCRIPTION = (
    "github_search_code searches code text confined to the bound repository and returns matching paths. "
    "The repository is fixed when the tool is built, so the model only supplies the query text and an optional branch. "
    "Queries cannot name another repository, and results are bounded in count with their source attached. "
    "Use it to locate relevant files before reading them."
)
_LIST_PATH_DESCRIPTION = "Repo-relative directory to list within the bound repository. Empty string selects the repository root for top-level discovery. Nested paths use forward slashes from the root downward. Only names directly inside the chosen directory are returned."
_READ_PATH_DESCRIPTION = "Repo-relative file to read within the bound repository. The value must name a file, never a directory or an external address. Forward slashes separate nested levels from the root downward. Paths escaping the repository are rejected before any request."
_SEARCH_QUERY_DESCRIPTION = "Code text to find within the bound repository. Matching is confined to the repository fixed at build time. Repository qualifiers are rejected so the scope cannot widen. Results return bounded matching paths with their source attached."
_REF_DESCRIPTION = "Branch or commit to read within the bound repository. Omit it to use the repository default branch for stable reads. Values are limited to safe branch characters only. Unrecognized refs fail validation before any request."


class SourceTool:
    """Builds repository-scoped agent tools from one external source dict."""

    def __init__(self, source: Mapping[str, Any], *, max_output_bytes: int = SOURCES_DEFAULT_MAX_OUTPUT_BYTES) -> None:
        """Coerce the public source dict and output bound into validated state."""
        self._config = SourceConfig.from_mapping(source)
        self._max_output_bytes = self._coerce_bound(max_output_bytes)
        self._require_repository()

    @property
    def config(self) -> SourceConfig:
        """Return the validated source these tools are bound to."""
        return self._config

    @property
    def max_output_bytes(self) -> int:
        """Return the per-response UTF-8 byte ceiling for built tools."""
        return self._max_output_bytes

    def build(self) -> list[BaseTool]:
        """Construct the deterministic list, read, and search tools for the bound repository."""
        client = create_client(self._config)
        return [GitHubListFilesTool(client, self._config, self._max_output_bytes), GitHubReadFileTool(client, self._config, self._max_output_bytes), GitHubSearchCodeTool(client, self._config, self._max_output_bytes)]

    def _require_repository(self) -> None:
        """Reject pull-request resources before any tool is built."""
        if self._config.kind != SourceKind.REPOSITORY:
            raise ConfigurationError("SourceTool requires a repository resource, not a pull request.")

    @staticmethod
    def _coerce_bound(max_output_bytes: int) -> int:
        """Accept one positive integer byte bound, rejecting loose or nonpositive values."""
        if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes <= 0:
            raise ConfigurationError("SourceTool 'max_output_bytes' must be a positive integer.")
        return max_output_bytes


class _ScopedGitHubTool(BaseTool):
    """Shared scope binding and request plumbing for one GitHub repository tool."""

    operation: str = "github"

    def __init__(self, client: SourceProviderClient, config: SourceConfig, max_output_bytes: int) -> None:
        """Close over the bound client, repository scope, and output ceiling."""
        self._client = client
        self._config = config
        self._max_output_bytes = max_output_bytes

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration, which never names the bound resource."""
        raise NotImplementedError

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate arguments, run the scoped request, and bound the payload."""
        raise NotImplementedError

    def validate_call(self, call: ToolCall) -> str | None:
        """Pre-check arguments and return an error string, or None when valid."""
        return super().validate_call(call)

    def _arguments(self, call: ToolCall) -> dict[str, Any]:
        """Read the call arguments as a plain dict for validation."""
        return dict(call.arguments) if isinstance(call.arguments, Mapping) else {}

    def _ref_of(self, args: dict[str, Any]) -> str | None:
        """Resolve the optional branch ref, rejecting scope-widening values."""
        raw = args.get("ref")
        if raw is None or raw == "":
            return None
        return validate_ref(raw)

    def _provenance(self) -> dict[str, str]:
        """Stamp every result with the provider, resource, and operation identity."""
        # @intent external boundaries
        # Provenance comes from construction scope only, so model input can never forge result identity.
        return {"provider": self._config.provider.value, "resource": f"{self._config.owner}/{self._config.repo}", "operation": self.operation}

    def _succeed(self, name: str, text: str) -> ToolResult:
        """Clip one payload to the byte ceiling and return it as a stamped success."""
        clipped = clip_text(text, self._max_output_bytes)
        metadata: dict[str, Any] = dict(self._provenance())
        metadata["truncated"] = clipped != text
        return ToolResult.success(name, clipped, metadata=metadata)

    def _fail(self, name: str, reason: str, error_type: str) -> ToolResult:
        """Return one stamped failure without leaking provider internals."""
        return ToolResult.failure(name, reason, metadata={**self._provenance(), "error_type": error_type})


def validate_repo_path(raw: Any) -> str:
    """Accept one repo-relative path, rejecting absolute paths, URLs, and escapes."""
    if not isinstance(raw, str) or not raw or len(raw) > SOURCES_MAX_PATH_CHARS:
        raise ConfigurationError("Tool 'path' must be a nonempty string within the length limit.")
    lowered = raw.strip().lower()
    if "://" in lowered or lowered.startswith(("http:", "https:", "git@", "/")):
        raise ConfigurationError("Tool 'path' must be repo-relative, never a URL or absolute path.")
    normalized = posixpath.normpath(raw.strip().replace("\\", "/")).lstrip("/")
    if normalized in ("", ".") or normalized.startswith("..") or "/../" in f"/{normalized}/":
        raise ConfigurationError("Tool 'path' must stay inside the bound repository.")
    return normalized


def validate_search_query(raw: Any) -> str:
    """Accept one search query, rejecting qualifiers that would widen the repository scope."""
    if not isinstance(raw, str) or not raw.strip() or len(raw) > SOURCES_MAX_QUERY_CHARS:
        raise ConfigurationError("Tool 'query' must be a nonempty string within the length limit.")
    if "repo:" in raw.lower():
        raise ConfigurationError("Tool 'query' must not name a repository; search stays in the bound repo.")
    return raw.strip()


class GitHubListFilesTool(_ScopedGitHubTool):
    """Lists directory names inside one bound GitHub repository."""

    operation = "list_files"

    def spec(self) -> ToolSpec:
        """Declare the directory listing contract with its optional path and branch."""
        return ToolSpec(name="github_list_files", description=_LIST_DESCRIPTION, parameters=(ToolParameter(name="path", type="string", description=_LIST_PATH_DESCRIPTION, required=False, default=""), ToolParameter(name="ref", type="string", description=_REF_DESCRIPTION, required=False, default=None)), permission=ToolPermission.SAFE, metadata={"source": "integrations", "provider": "github", "operation": self.operation})

    async def execute(self, call: ToolCall) -> ToolResult:
        """List one validated directory through the bound repository scope."""
        args = self._arguments(call)
        try:
            path = self._directory_of(args.get("path", ""))
            ref = self._ref_of(args)
            text = await self._client.list_repo_files(self._config, path, ref, max_entries=SOURCES_MAX_DIRECTORY_ENTRIES)
        except ConfigurationError as exc:
            return self._fail("github_list_files", str(exc), "validation")
        except Exception as exc:
            return self._fail("github_list_files", f"The provider request failed with {type(exc).__name__}.", type(exc).__name__)
        return self._succeed("github_list_files", text)

    def validate_call(self, call: ToolCall) -> str | None:
        """Report argument problems before execution without touching the network."""
        base = super().validate_call(call)
        if base is not None:
            return base
        try:
            self._directory_of(self._arguments(call).get("path", ""))
        except ConfigurationError as exc:
            return str(exc)
        return None

    @staticmethod
    def _directory_of(raw: Any) -> str:
        """Accept an empty root marker or one validated repo-relative directory."""
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return ""
        return validate_repo_path(raw)


class GitHubReadFileTool(_ScopedGitHubTool):
    """Reads one file's text inside one bound GitHub repository."""

    operation = "read_file"

    def spec(self) -> ToolSpec:
        """Declare the file read contract with its required path and optional branch."""
        return ToolSpec(name="github_read_file", description=_READ_DESCRIPTION, parameters=(ToolParameter(name="path", type="string", description=_READ_PATH_DESCRIPTION, required=True), ToolParameter(name="ref", type="string", description=_REF_DESCRIPTION, required=False, default=None)), permission=ToolPermission.SAFE, metadata={"source": "integrations", "provider": "github", "operation": self.operation})

    async def execute(self, call: ToolCall) -> ToolResult:
        """Read one validated file through the bound repository scope."""
        args = self._arguments(call)
        try:
            path = validate_repo_path(args.get("path"))
            ref = self._ref_of(args)
            text = await self._client.read_repo_file(self._config, path, ref, max_bytes=self._max_output_bytes)
        except ConfigurationError as exc:
            return self._fail("github_read_file", str(exc), "validation")
        except Exception as exc:
            return self._fail("github_read_file", f"The provider request failed with {type(exc).__name__}.", type(exc).__name__)
        return self._succeed("github_read_file", text)

    def validate_call(self, call: ToolCall) -> str | None:
        """Report argument problems before execution without touching the network."""
        base = super().validate_call(call)
        if base is not None:
            return base
        try:
            validate_repo_path(self._arguments(call).get("path"))
        except ConfigurationError as exc:
            return str(exc)
        return None


class GitHubSearchCodeTool(_ScopedGitHubTool):
    """Searches code text confined to one bound GitHub repository."""

    operation = "search_code"

    def spec(self) -> ToolSpec:
        """Declare the code search contract with its required query and optional branch."""
        return ToolSpec(name="github_search_code", description=_SEARCH_DESCRIPTION, parameters=(ToolParameter(name="query", type="string", description=_SEARCH_QUERY_DESCRIPTION, required=True), ToolParameter(name="ref", type="string", description=_REF_DESCRIPTION, required=False, default=None)), permission=ToolPermission.SAFE, metadata={"source": "integrations", "provider": "github", "operation": self.operation})

    async def execute(self, call: ToolCall) -> ToolResult:
        """Search one validated query confined to the bound repository scope."""
        args = self._arguments(call)
        try:
            query = validate_search_query(args.get("query"))
            ref = self._ref_of(args)
            text = await self._client.search_repo_code(self._config, query, ref, max_items=SOURCES_MAX_SEARCH_ITEMS)
        except ConfigurationError as exc:
            return self._fail("github_search_code", str(exc), "validation")
        except Exception as exc:
            return self._fail("github_search_code", f"The provider request failed with {type(exc).__name__}.", type(exc).__name__)
        return self._succeed("github_search_code", text)

    def validate_call(self, call: ToolCall) -> str | None:
        """Report argument problems before execution without touching the network."""
        base = super().validate_call(call)
        if base is not None:
            return base
        try:
            validate_search_query(self._arguments(call).get("query"))
        except ConfigurationError as exc:
            return str(exc)
        return None


__all__ = [
    "GitHubListFilesTool",
    "GitHubReadFileTool",
    "GitHubSearchCodeTool",
    "SourceTool",
    "validate_repo_path",
    "validate_search_query",
]
