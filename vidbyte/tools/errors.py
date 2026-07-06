"""Context Protocol Header

Description:
    Defines structured, tool-authorable errors and normalization helpers.
Purpose:
    Lets tools raise classified errors with remediation hints while keeping
    runtime and standalone executor error metadata consistent.
Architecture:
    - ToolError: Tool-authored exception carrying kind, hint, and retryability.
    - ToolErrorNormalizer: Converts known exception surfaces into ToolResult objects.
Relations:
    Related to vidbyte.tools.base, vidbyte.tools.executor, and vidbyte.agents.runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.tools import ToolErrorKind, ToolResult, ToolSpec
from vidbyte.lib.errors import McpToolExecutionError, VidbyteSdkError


class ToolError(VidbyteSdkError):
    """Structured exception raised by tool authors for model-visible failures."""

    def __init__(self, message: str, *, kind: ToolErrorKind, hint: str | None = None, retryable: bool | None = None, details: Mapping[str, Any] | None = None) -> None:
        # Stores the tool-authored message plus stable classification metadata.
        metadata = ToolErrorNormalizer.metadata_for(kind, hint=hint, retryable=retryable)
        super().__init__(message, details={**dict(details or {}), **metadata})
        self.kind = kind
        self.hint = hint
        self.retryable = retryable


class ToolErrorNormalizer:
    """Normalizes tool pipeline exceptions into stable ToolResult metadata."""

    def __init__(self, spec: ToolSpec | None = None) -> None:
        # Stores optional spec-level fallback context for bare tool exceptions.
        self.spec = spec

    def from_validation_error(self, tool_name: str, message: str) -> ToolResult:
        # Converts schema or argument validation failures into invalid-arguments results.
        return ToolResult.error(
            tool_name,
            message,
            metadata=self.metadata_for(ToolErrorKind.INVALID_ARGUMENTS),
        )

    def from_tool_error(self, tool_name: str, exc: ToolError) -> ToolResult:
        # Preserves a tool-authored structured error exactly, using spec hints as fallback.
        return ToolResult.error(
            tool_name,
            exc.message,
            metadata=self.metadata_for(
                exc.kind,
                hint=exc.hint or self.default_error_hint(),
                retryable=exc.retryable,
                extra=exc.details,
            ),
        )

    def from_mcp_tool_execution_error(self, tool_name: str, exc: McpToolExecutionError) -> ToolResult:
        # Classifies runtime MCP execution failures as retryable upstream errors.
        return ToolResult.error(
            tool_name,
            f"Tool execution failed: {exc}",
            metadata=self.metadata_for(
                ToolErrorKind.UPSTREAM_ERROR,
                hint=self.default_error_hint(),
                retryable=True,
                extra={"error_type": type(exc).__name__},
            ),
        )

    def from_plain_exception(self, tool_name: str, exc: Exception) -> ToolResult:
        # Converts backward-compatible bare exceptions into execution-failed results.
        return ToolResult.error(
            tool_name,
            f"Tool execution failed: {exc}",
            metadata=self.metadata_for(
                ToolErrorKind.EXECUTION_FAILED,
                hint=self.default_error_hint(),
                extra={"error_type": type(exc).__name__},
            ),
        )

    def default_error_hint(self) -> str | None:
        # Returns the spec fallback hint for bare or under-specified tool failures.
        if self.spec is None:
            return None
        return self.spec.default_error_hint

    @staticmethod
    def metadata_for(kind: ToolErrorKind, *, hint: str | None = None, retryable: bool | None = None, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        # Builds the canonical metadata payload consumed by render and policy layers.
        metadata = {"error": kind.value}
        if hint:
            metadata["hint"] = hint
        if retryable is not None:
            metadata["retryable"] = retryable
        metadata.update(dict(extra or {}))
        metadata["error"] = kind.value
        return metadata
