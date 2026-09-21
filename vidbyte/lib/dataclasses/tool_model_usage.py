"""FILE: vidbyte/lib/dataclasses/tool_model_usage.py

PURPOSE: Defines ToolModelCall, the record a model-backed tool attaches to its result for each model call it made, so the agent's UsageTracker can price it.
ROLE IN CODEBASE: `vidbyte/tools/model_backed.py` embeds these records in ToolResult metadata and `AgentRuntime._record_tool_model_usage` feeds each one to `UsageTracker.record_call`.
ARCHITECTURE NOTE: The field names (provider, model, usage) are exactly the attributes UsageTracker.record_call duck-types, so no adapter object sits between a tool and the ledger.
COMMON MODIFICATION PATTERNS: Keep the three duck-typed attribute names stable; add optional fields only if UsageTracker learns to read them.
KNOWN EDGE CASES: usage is the provider's raw usage mapping and may be empty; the provider's ProviderUsage parser decides whether it is priceable.
RELATED DOCS: docs/design/jev-decide-tool.md and field-guide/vidbyte-sdk/runtime-boundaries.md.
TESTS: tests/test_jev_decide_tool.py and scripts/test_jev_decide_tool.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class ToolModelCall:
    """One model call a tool made on the agent's behalf, in the shape UsageTracker records."""

    provider: ModelProvider
    model: str
    usage: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Requires a real provider enum and model name, and freezes the usage mapping.
        # @intent ledger-rows-are-well-typed
        # UsageTracker prices by provider enum; rejecting a raw string here keeps a tool from
        # writing an unpriceable row that would silently flip cost_complete to False.
        if not isinstance(self.provider, ModelProvider):
            raise ConfigurationError("ToolModelCall.provider must be a ModelProvider.")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ConfigurationError("ToolModelCall.model must be a non-empty string.")
        if not isinstance(self.usage, Mapping):
            raise ConfigurationError("ToolModelCall.usage must be a mapping.")
        object.__setattr__(self, "usage", MappingProxyType(dict(self.usage)))


__all__ = ["ToolModelCall"]
