"""Context Protocol Header

Description:
    Defines AgentFallback, the ordered model chain an agent routes through when a
    model call fails, plus the transforms that rebuild provider-derived run state.
Purpose:
    Lets a developer declare prioritized backup models once at construction so a
    transient provider failure degrades to the next model instead of ending the run.
Architecture:
    - AgentFallback: Immutable chain plus advance/transform policy helpers.
    - FallbackTransform: Rebuilt handle, provider, tool schemas, and transcript.
    - DEFAULT_FALLBACK_ERRORS: Provider-level exceptions that justify a switch.
Relations:
    Built by vidbyte.agents.base from AgentFallbackSettings. Consumed by
    vidbyte.agents.runtime inside the direct model/tool loop.
Similar Files:
    - vidbyte/agents/settings/fallback.py: Developer-facing settings that build this.
    - vidbyte/lib/dataclasses/runner.py: RunnerHandle.with_runner is the swap primitive.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.agents import FallbackModel
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderSelectionError,
    UnsupportedProviderError,
)
from vidbyte.lib.runners import Runner
from vidbyte.lib.tools.formatter import ToolsFormatter

if TYPE_CHECKING:
    from vidbyte.tools.catalog import Tools


# Provider-level failures only. Tool, permission, and configuration errors are the
# agent's own problem and are never made better by calling a different model.
DEFAULT_FALLBACK_ERRORS: tuple[type[BaseException], ...] = (
    ProviderRequestError,
    ProviderResponseError,
    ProviderConfigurationError,
    ProviderSelectionError,
    UnsupportedProviderError,
    TimeoutError,
)


@dataclass(frozen=True, slots=True)
class FallbackTransform:
    """Rebuilt provider-derived state for the model a run is switching to."""

    index: int
    handle: RunnerHandle
    provider: str
    tool_schemas: tuple[dict[str, Any], ...]
    messages: list[dict[str, Any]]
    context_reset: bool
    model: FallbackModel = field(repr=False)


class AgentFallback:
    """Ordered model chain plus the transforms that route an in-flight run to the next model."""

    def __init__(self, models: Sequence[FallbackModel], *, fallback_on: tuple[type[BaseException], ...] = DEFAULT_FALLBACK_ERRORS) -> None:
        # Stores the chain (index 0 is the primary) and caches runners lazily, keyed by chain index.
        if not models:
            raise ConfigurationError("AgentFallback requires at least the primary model in its chain.")
        self.models = tuple(models)
        self.fallback_on = tuple(fallback_on)
        self._runner_cache: dict[int, object] = {}

    def advance(self, error: BaseException, index: int) -> int | None:
        """Return the next chain index to try, or None when this run must stop falling back."""
        if not isinstance(error, self.fallback_on):
            return None
        if index + 1 >= len(self.models):
            return None
        return index + 1

    def transform(self, handle: RunnerHandle, provider: str, tools: Tools, messages: list[dict[str, Any]], index: int) -> FallbackTransform:
        """Rebuild the handle, provider, tool schemas, and transcript for the model at index."""
        target = self.model_at(index)
        next_handle = handle.with_runner(self.build_runner(index), target.provider)
        compatible = self.is_wire_compatible(provider, target.provider)
        return FallbackTransform(
            index=index,
            handle=next_handle,
            provider=target.provider,
            tool_schemas=ToolsFormatter.format_tools(tools, target.provider),
            messages=list(messages) if compatible else [],
            context_reset=not compatible,
            model=target,
        )

    def build_runner(self, index: int) -> object:
        """Build and memoize the executable runner for the model at index."""
        if index not in self._runner_cache:
            target = self.model_at(index)
            self._runner_cache[index] = Runner.from_model(
                provider=target.provider,
                model_name=target.model,
                api_key=target.api_key,
                temperature=target.temperature,
            ).build()
        return self._runner_cache[index]

    def is_wire_compatible(self, source: str, target: str) -> bool:
        """Report whether two providers speak the same request/response payload shape."""
        return ToolsFormatter.wire_format(source) == ToolsFormatter.wire_format(target)

    def model_at(self, index: int) -> FallbackModel:
        """Return the chain entry at index, raising a clear error when it is out of range."""
        if not 0 <= index < len(self.models):
            raise ConfigurationError(f"Fallback chain index {index} is out of range for a chain of {len(self.models)}.")
        return self.models[index]

    def __len__(self) -> int:
        """Return the chain length, including the primary model."""
        return len(self.models)

    def __repr__(self) -> str:
        """Return the ordered chain identities without exposing any credentials."""
        chain = " -> ".join(model.identity() for model in self.models)
        return f"AgentFallback({chain})"


__all__ = ["AgentFallback", "FallbackTransform", "DEFAULT_FALLBACK_ERRORS"]
