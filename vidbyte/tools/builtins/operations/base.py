"""Context Protocol Header

Description:
    Abstract base for tools whose execution incurs a priced search/fetch operation.
Purpose:
    Carries the stable (operation, provider) identity the runtime uses to price a
    tool call, derives the per-call mode / units / attempts / provider-reported
    cost from the result without any mutable per-call state, and binds the
    optional provider client that performs the vendor request.
Architecture:
    - PricedOperationTool: BaseTool subclass adding operation/provider ClassVars,
      the mode_used / units_used / attempts_used / reported_cost_usd hooks the
      runtime reads, and the executed / failed / contract result builders.
Relations:
    Subclassed by the search and fetch tools in this package; executes through
    vidbyte/tools/builtins/operations/clients; detected by
    AgentRuntime._record_operation_usage and priced via UsageTracker.record_operation
    against vidbyte/lib/registries/operation_pricing.py.
Similar Files:
    - vidbyte/tools/builtins/document_retrieval.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.operations.clients import WebOperationClient
from vidbyte.tools.types import ToolResult


class PricedOperationTool(BaseTool):
    """Base for a tool whose call is billed as one search/fetch operation."""

    operation: ClassVar[str] = ""
    provider: ClassVar[str] = ""

    _USAGE_KEY: ClassVar[str] = "operation_usage"
    _PAYLOAD_KEY: ClassVar[str] = "operation_payload"

    def __init__(self, *, client: WebOperationClient | None = None) -> None:
        # Binds the executing provider client; without one the tool returns a priced contract stub.
        self._client = client

    def mode_used(self, call: object, result: ToolResult) -> str:
        # Returns the billing mode for this call, read from the result's usage annotation.
        raw = self._operation_usage(result).get("mode", "default")
        return raw if isinstance(raw, str) and raw.strip() else "default"

    def units_used(self, call: object, result: ToolResult) -> int:
        # Returns the number of billable units, read from the result's usage annotation.
        raw = self._operation_usage(result).get("units", 1)
        return raw if isinstance(raw, int) and not isinstance(raw, bool) else 1

    def attempts_used(self, call: object, result: ToolResult) -> int:
        # Returns how many provider attempts this call spent, so retries stay billable.
        raw = self._operation_usage(result).get("attempts", 1)
        return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else 1

    def reported_cost_usd(self, call: object, result: ToolResult) -> float | None:
        # Returns a provider-reported USD cost when the result carries one, else None.
        raw = self._operation_usage(result).get("reported_cost_usd")
        return float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None

    def _contract_result(self, summary: str, *, units: int = 1, mode: str = "default", reported_cost_usd: float | None = None) -> ToolResult:
        # Builds a deterministic priced-contract result carrying the billing annotation;
        # a real provider client replaces the body while keeping this usage metadata shape.
        return ToolResult.success(self.name, summary, metadata=self._usage_metadata(units=units, mode=mode, attempts=1, reported_cost_usd=reported_cost_usd))

    def _executed_result(self, summary: str, payload: object, *, units: int, mode: str, attempts: int) -> ToolResult:
        # Builds a success result carrying the model-facing summary and the typed payload.
        metadata = self._usage_metadata(units=units, mode=mode, attempts=attempts)
        metadata[self._PAYLOAD_KEY] = payload
        return ToolResult.success(self.name, summary, metadata=metadata)

    def _failed_result(self, message: str, *, units: int, mode: str, attempts: int, error: str) -> ToolResult:
        # Builds an error result that still declares the attempts the retry policy spent.
        metadata = self._usage_metadata(units=units, mode=mode, attempts=attempts)
        metadata["error"] = error
        return ToolResult.error(self.name, message, metadata=metadata)

    @classmethod
    def _operation_usage(cls, result: ToolResult) -> Mapping[str, Any]:
        # Extracts the operation-usage annotation embedded in a tool result's metadata.
        metadata = getattr(result, "metadata", None)
        if not isinstance(metadata, Mapping):
            return {}
        usage = metadata.get(cls._USAGE_KEY)
        return usage if isinstance(usage, Mapping) else {}

    @classmethod
    def declares_usage(cls, result: ToolResult) -> bool:
        # True when the tool explicitly annotated this result for billing.
        return bool(cls._operation_usage(result))

    @classmethod
    def _usage_metadata(cls, *, units: int = 1, mode: str = "default", attempts: int = 1, reported_cost_usd: float | None = None) -> dict[str, Any]:
        # Builds the metadata a subclass merges into its ToolResult so the runtime can
        # price the operation from the result alone, keeping the tool stateless.
        payload: dict[str, Any] = {"operation": cls.operation, "provider": cls.provider, "mode": mode, "units": units, "attempts": attempts}
        if reported_cost_usd is not None:
            payload["reported_cost_usd"] = reported_cost_usd
        return {cls._USAGE_KEY: payload}


__all__ = ["PricedOperationTool"]
