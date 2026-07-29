"""Context Protocol Header

Description:
    Shared typed adapter for provider endpoints beyond normalized search/fetch.
Purpose:
    Lets each provider expose documented API capabilities with explicit tool
    schemas while keeping request execution, charge metadata, and redaction common.
Architecture:
    ProviderApiTool resolves a fixed endpoint path, builds a bounded request body,
    delegates to the injected provider client, and renders a safe payload summary.
Relations:
    Subclassed by provider endpoint tools and priced by PricedOperationTool hooks.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar

from vidbyte.lib.dataclasses.operations import OperationCharge, ProviderOperationPayload
from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError
from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class ProviderApiTool(PricedOperationTool):
    """Model-facing adapter for one documented provider API endpoint."""

    tool_name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    parameters: ClassVar[tuple[ToolParameter, ...]] = ()
    method: ClassVar[str] = "POST"
    path: ClassVar[str] = ""
    path_parameters: ClassVar[tuple[str, ...]] = ()
    charge_operation: ClassVar[str | None] = None
    charge_mode: ClassVar[str] = "default"
    charge_meter: ClassVar[str] = "request"
    charge_units: ClassVar[float] = 1
    billable: ClassVar[bool] = True
    permission: ClassVar[ToolPermission] = ToolPermission.READ

    def spec(self) -> ToolSpec:
        # Declares the provider endpoint with its explicit model-facing parameters.
        return ToolSpec(name=self.tool_name, description=self.description, parameters=self.parameters, permission=self.permission)

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validates the injected client, calls the endpoint, and returns a redacted summary.
        if self._client is None:
            if not self.billable:
                return ToolResult.success(self.name, f"{self.provider} {self.operation} contract")
            return self._contract_result(f"{self.provider} {self.operation} contract", units=self.charge_units, mode=self.charge_mode)
        try:
            payload = await self._request(call)
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result(f"{self.provider} {self.operation} failed.", units=self.charge_units, mode=self.charge_mode, attempts=self._client.max_attempts, error="provider_request_failed")
        except (KeyError, TypeError, ValueError):
            return self._failed_result(f"{self.provider} {self.operation} input was invalid.", units=0, mode=self.charge_mode, attempts=0, error="invalid_provider_arguments")
        return self._payload_result(self._render(payload), payload, attempts=payload.attempts)

    async def _request(self, call: ToolCall) -> ProviderOperationPayload:
        # Builds the endpoint body and delegates the vendor request to the injected client.
        body = {key: value for key, value in call.arguments.items() if key not in self.path_parameters and value is not None}
        resolved_path = self.path.format(**{key: call.arguments.get(key, "") for key in self.path_parameters})
        charges = self._charges(call)
        return await self._client.api(self.operation, method=self.method, path=resolved_path, body=body or None, charges=charges)

    def _charges(self, call: ToolCall) -> tuple[OperationCharge, ...]:
        # Creates the fixed pricebook component declared by this endpoint adapter.
        del call
        if not self.billable or self.charge_operation is None:
            return ()
        return (OperationCharge(self.charge_operation, self.provider, mode=self.charge_mode, meter=self.charge_meter, units=self.charge_units),)

    def _render(self, payload: ProviderOperationPayload) -> str:
        # Renders bounded provider data while omitting secrets and session capabilities.
        safe = self._safe_value(payload.data)
        text = json.dumps(safe, ensure_ascii=False, default=str)
        if len(text) > 4000:
            text = f"{text[:4000]}...[truncated]"
        identity = payload.async_id or payload.request_id or "none"
        return f"{self.provider} {self.operation} completed (id={identity}).\n{text}"

    @classmethod
    def _safe_value(cls, value: Any) -> Any:
        # Recursively removes credential-like fields and sensitive browser capabilities.
        if isinstance(value, Mapping):
            return {str(key): cls._safe_value(item) for key, item in value.items() if not cls._is_secret_key(str(key))}
        if isinstance(value, (list, tuple)):
            return [cls._safe_value(item) for item in value[:50]]
        if isinstance(value, str) and (value.startswith("ws") or "connect" in value.lower() and "url" in value.lower()):
            return "[redacted]"
        return value

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        # Identifies credential, cookie, proxy, and browser-session capability fields.
        upper = key.upper()
        return any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "COOKIE", "PROXY_AUTH", "CONNECT_URL"))


__all__ = ["ProviderApiTool"]
