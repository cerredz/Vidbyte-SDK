"""FILE: vidbyte/tools/builtins/operations/base.py

PURPOSE:
    Defines the stateless priced-operation contract and the application executor
    seam shared by SDK search and fetch tools.
ROLE IN CODEBASE:
    Search and fetch tools subclass PricedOperationTool. AgentRuntime reads its
    operation metadata and UsageTracker prices the result through the operation
    pricing registry.
ARCHITECTURE NOTE:
    The SDK owns tool schemas and billing identity; applications inject provider
    I/O as one async executor returning ToolResult.
FUNCTION INVENTORY:
    PricedOperationTool: delegates calls, normalizes results, and exposes usage
    hooks consumed by AgentRuntime.
COMMON MODIFICATION PATTERNS:
    Add shared result behavior here; keep provider arguments and unit selection in
    the concrete operation module.
WHAT NOT TO DO IN THIS FILE:
    1. Do not store credentials or provider clients.
    2. Do not trust executor-supplied operation_usage metadata.
KNOWN EDGE CASES:
    Executor failures are converted into redacted priced error results so failed
    provider attempts remain observable without leaking exception messages.
RELATED DOCS:
    tests/features/priced_operation_executor/FEATURE.md
TESTS:
    tests/features/priced_operation_executor/test_contract.py
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, ClassVar, TypeAlias

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolResult

OperationExecutor: TypeAlias = Callable[[ToolCall], Awaitable[ToolResult]]


class PricedOperationTool(BaseTool):
    """Base for a tool whose call is billed as one search/fetch operation."""

    operation: ClassVar[str] = ""
    provider: ClassVar[str] = ""

    _USAGE_KEY: ClassVar[str] = "operation_usage"

    def __init__(self, *, executor: OperationExecutor | None = None) -> None:
        self._executor = executor

    async def _execute_or_contract(
        self,
        call: ToolCall,
        summary: str,
        *,
        units: int = 1,
        mode: str = "default",
        reported_cost_usd: float | None = None,
    ) -> ToolResult:
        if self._executor is None:
            return self._contract_result(
                summary,
                units=units,
                mode=mode,
                reported_cost_usd=reported_cost_usd,
            )
        try:
            result = await self._executor(call)
        # External executors may use any provider exception hierarchy. Normalize
        # every failure here so usage remains billable and secret text stays out.
        except Exception as exc:  # noqa: BLE001
            result = ToolResult.error(
                self.name,
                "Operation executor failed.",
                metadata={
                    "error": "operation_executor_error",
                    "error_type": type(exc).__name__,
                },
            )
        return self._priced_result(
            result,
            units=units,
            mode=mode,
            reported_cost_usd=reported_cost_usd,
        )

    def mode_used(self, call: object, result: ToolResult) -> str:
        # Returns the billing mode for this call, read from the result's usage annotation.
        raw = self._operation_usage(result).get("mode", "default")
        return raw if isinstance(raw, str) and raw.strip() else "default"

    def units_used(self, call: object, result: ToolResult) -> int:
        # Returns the number of billable units, read from the result's usage annotation.
        raw = self._operation_usage(result).get("units", 1)
        return raw if isinstance(raw, int) and not isinstance(raw, bool) else 1

    def reported_cost_usd(self, call: object, result: ToolResult) -> float | None:
        # Returns a provider-reported USD cost when the result carries one, else None.
        raw = self._operation_usage(result).get("reported_cost_usd")
        return float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None

    def _contract_result(
        self,
        summary: str,
        *,
        units: int = 1,
        mode: str = "default",
        reported_cost_usd: float | None = None,
    ) -> ToolResult:
        # Builds a deterministic priced-contract result carrying the billing annotation;
        # a real provider client replaces the body while keeping this usage metadata shape.
        return self._priced_result(
            ToolResult.success(self.name, summary),
            units=units,
            mode=mode,
            reported_cost_usd=reported_cost_usd,
        )

    def _priced_result(
        self,
        result: ToolResult,
        *,
        units: int,
        mode: str,
        reported_cost_usd: float | None,
    ) -> ToolResult:
        metadata = dict(result.metadata)
        metadata.update(
            self._usage_metadata(
                units=units,
                mode=mode,
                reported_cost_usd=reported_cost_usd,
            )
        )
        return ToolResult(
            tool_name=self.name,
            status=result.status,
            output=result.output,
            metadata=metadata,
        )

    @classmethod
    def _operation_usage(cls, result: ToolResult) -> Mapping[str, Any]:
        # Extracts the operation-usage annotation embedded in a tool result's metadata.
        metadata = getattr(result, "metadata", None)
        if not isinstance(metadata, Mapping):
            return {}
        usage = metadata.get(cls._USAGE_KEY)
        return usage if isinstance(usage, Mapping) else {}

    @classmethod
    def _usage_metadata(cls, *, units: int = 1, mode: str = "default", reported_cost_usd: float | None = None) -> dict[str, Any]:
        # Builds the metadata a subclass merges into its ToolResult so the runtime can
        # price the operation from the result alone, keeping the tool stateless.
        payload: dict[str, Any] = {"operation": cls.operation, "provider": cls.provider, "mode": mode, "units": units}
        if reported_cost_usd is not None:
            payload["reported_cost_usd"] = reported_cost_usd
        return {cls._USAGE_KEY: payload}


__all__ = ["OperationExecutor", "PricedOperationTool"]
