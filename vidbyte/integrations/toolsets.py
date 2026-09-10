"""FILE: vidbyte/integrations/toolsets.py

PURPOSE: Turns a provider adapter's declared capabilities into agent tools permanently bound to one resource.
ROLE IN CODEBASE: The tools half of the Sources layer, and the reason an agent granted one resource cannot address a sibling resource.
ARCHITECTURE NOTE: The resource lives in a construction-time closure and in spec metadata, never as a model-fillable tool parameter.
COMMON MODIFICATION PATTERNS: Add an operation to ProviderOperation and let the adapter describe it; the toolset needs no change to expose it.
KNOWN EDGE CASES: Two selections on one provider must not collide on tool name, an adapter spec declaring a resource parameter is rejected, and budget exhaustion fails the call rather than raising.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test_sources_access_layer.py.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re

from vidbyte.integrations.adapters import ProviderAdapter
from vidbyte.integrations.budget import ToolBudget
from vidbyte.lib.constants.integrations import (
    INTEGRATIONS_MAX_TOOL_NAME_RESOURCE_CHARS,
    INTEGRATIONS_RESERVED_TOOL_PARAMETERS,
    INTEGRATIONS_RESOURCE_HASH_CHARS,
)
from vidbyte.lib.dataclasses.integrations import Credentials, ResourceScope
from vidbyte.lib.enums.integrations import ProviderOperation
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_UNSAFE_NAME_CHARS = re.compile(r"[^a-z0-9_]+")


class ScopedProviderTool(BaseTool):
    """One provider read operation bound to a single resource for the life of a run."""

    def __init__(self, *, adapter: ProviderAdapter, operation: ProviderOperation, scope: ResourceScope, credentials: Credentials, budget: ToolBudget, spec: ToolSpec) -> None:
        # The scope and credentials are closed over here so no call argument can redirect them.
        self._adapter = adapter
        self._operation = operation
        self._scope = scope
        self._credentials = credentials
        self._budget = budget
        self._spec = spec

    @property
    def scope(self) -> ResourceScope:
        """Return the immutable resource this tool is bound to."""
        return self._scope

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration, which never names the bound resource."""
        return self._spec

    async def execute(self, call: ToolCall) -> ToolResult:
        """Charge the budget, invoke the adapter against the bound scope, and stamp provenance."""
        if not self._budget.charge(len(str(call.arguments))):
            return ToolResult.failure(self._spec.name, "The exploration budget for this run is exhausted.", metadata={"error": "budget_exhausted", **self._provenance()})
        try:
            output = await self._invoke(call)
        except Exception as exc:
            return ToolResult.failure(self._spec.name, f"The provider request failed with {type(exc).__name__}.", metadata={"error": "provider_failed", "error_type": type(exc).__name__, **self._provenance()})
        return ToolResult.success(self._spec.name, output, metadata=self._provenance())

    async def _invoke(self, call: ToolCall) -> str:
        """Run the adapter operation for this call against the closed-over resource scope."""
        # @intent external boundaries
        # The scope and credentials come from construction, never from the call, so
        # a model cannot widen the request by supplying a different resource.
        return await self._adapter.invoke(self._operation, self._scope, self._credentials, dict(call.arguments))

    def _provenance(self) -> dict[str, str]:
        """Return the source identity stamped onto every result this tool returns."""
        return {
            "provider": self._scope.provider,
            "resource_id": self._scope.resource_id,
            "connection_id": self._scope.connection_id,
            "operation": self._operation.value,
        }


class ProviderToolset:
    """Builds the complete set of resource-scoped tools one selection contributes."""

    @staticmethod
    def build(*, adapter: ProviderAdapter, scope: ResourceScope, credentials: Credentials, budget: ToolBudget) -> tuple[ScopedProviderTool, ...]:
        """Build one scoped tool per capability the adapter declares, in deterministic order."""
        capabilities = adapter.capabilities()
        operations = tuple(operation for operation in ProviderOperation if operation in capabilities)
        return tuple(
            ScopedProviderTool(
                adapter=adapter,
                operation=operation,
                scope=scope,
                credentials=credentials,
                budget=budget,
                spec=ProviderToolset._bind_spec(adapter.describe_operation(operation), operation, scope),
            )
            for operation in operations
        )

    @staticmethod
    def _bind_spec(spec: ToolSpec, operation: ProviderOperation, scope: ResourceScope) -> ToolSpec:
        """Rewrite an adapter's spec into a uniquely named, resource-stamped, read-only tool."""
        # @intent permissions
        # The resource id is written into spec metadata rather than parameters because
        # ResourceScopePolicy reads the spec, so the value it authorizes against can
        # never be supplied or altered by the model.
        ProviderToolset._reject_resource_parameters(spec, scope)
        metadata = dict(spec.metadata)
        metadata["resource_id"] = scope.qualified_id()
        metadata["provider"] = scope.provider
        metadata["connection_id"] = scope.connection_id
        return dataclasses.replace(
            spec,
            name=ProviderToolset.tool_name(scope, operation),
            permission=ToolPermission.READ,
            metadata=metadata,
        )

    @staticmethod
    def _reject_resource_parameters(spec: ToolSpec, scope: ResourceScope) -> None:
        """Raise when an adapter spec lets the model address the resource itself."""
        offenders = tuple(parameter.name for parameter in spec.parameters if parameter.name in INTEGRATIONS_RESERVED_TOOL_PARAMETERS)
        if offenders:
            raise ConfigurationError(
                f"Adapter '{scope.provider}' declares reserved resource-addressing parameter(s) {', '.join(offenders)} "
                f"on operation tool '{spec.name}'. A scoped tool binds its resource at construction and must not accept one."
            )

    @staticmethod
    def tool_name(scope: ResourceScope, operation: ProviderOperation) -> str:
        """Build a deterministic tool name unique to one provider, resource, and operation."""
        return f"{ProviderToolset._sanitize(scope.provider)}_{operation.value}_{ProviderToolset._resource_slug(scope)}"

    @staticmethod
    def _resource_slug(scope: ResourceScope) -> str:
        """Build a short, collision-resistant slug for one resource id."""
        digest = hashlib.sha256(scope.resource_id.encode("utf-8")).hexdigest()[:INTEGRATIONS_RESOURCE_HASH_CHARS]
        sanitized = ProviderToolset._sanitize(scope.resource_id)[:INTEGRATIONS_MAX_TOOL_NAME_RESOURCE_CHARS].strip("_")
        return f"{sanitized}_{digest}" if sanitized else digest

    @staticmethod
    def _sanitize(value: str) -> str:
        """Reduce arbitrary text to the lowercase characters a tool name may contain."""
        return _UNSAFE_NAME_CHARS.sub("_", value.lower())


__all__ = [
    "ProviderToolset",
    "ScopedProviderTool",
]
