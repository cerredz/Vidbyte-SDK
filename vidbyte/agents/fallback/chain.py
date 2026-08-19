"""Context Protocol Header

Description:
    Defines AgentFallback, the ordered model chain an agent routes through when a
    model call fails or a per-hop policy elects to advance, plus the transforms
    that rebuild provider-derived run state.
Purpose:
    Lets a developer declare prioritized backup models once at construction so a
    transient provider failure, a slow call, or a cost overrun degrades to the
    next model instead of ending the run or silently overspending.
Architecture:
    - AgentFallback: Immutable chain plus advance/transform policy helpers.
    - DEFAULT_FALLBACK_ERRORS: Provider-level exceptions that justify a switch.
Relations:
    Built by vidbyte.agents.fallback.settings.AgentFallbackSettings.to_fallback.
    Consumed by vidbyte.agents.runtime inside the direct model/tool loop.
Similar Files:
    - vidbyte/agents/fallback/settings.py: Developer-facing settings that build this.
    - vidbyte/agents/fallback/policies.py: Per-hop LatencyPolicy and CostBudgetPolicy.
    - vidbyte/lib/dataclasses/agents.py: FallbackModel and FallbackTransform data contracts.
    - vidbyte/lib/dataclasses/runner.py: RunnerHandle.with_runner is the swap primitive.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.agents import FallbackModel, FallbackTransform
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderSelectionError,
    UnsupportedProviderError,
)
from vidbyte.lib.tools.formatter import ToolsFormatter

if TYPE_CHECKING:
    from vidbyte.agents.fallback.settings import AgentFallbackSettings
    from vidbyte.lib.dataclasses.agents import AgentRunnerConfig
    from vidbyte.lib.dataclasses.tools import ToolCallContext
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


class AgentFallback:
    """Ordered model chain plus the transforms that route an in-flight run to the next model."""

    def __init__(self, models: Sequence[FallbackModel], *, fallback_on: tuple[type[BaseException], ...] = DEFAULT_FALLBACK_ERRORS, policies: Sequence[object] = ()) -> None:
        # Stores the chain (index 0 is the primary) and caches runners lazily, keyed by chain index.
        if not models:
            raise ConfigurationError("AgentFallback requires at least the primary model in its chain.")
        self.models = tuple(models)
        self.fallback_on = tuple(fallback_on)
        self.policies = tuple(policies)
        self._runner_cache: dict[int, object] = {}

    @classmethod
    def from_spec(
        cls,
        spec: Sequence[str | FallbackModel] | AgentFallbackSettings | None,
        *,
        runner_config: AgentRunnerConfig,
        agent_name: str,
    ) -> AgentFallback | None:
        """Build the chain for an agent from its constructor spec, or None when unset.

        Accepts either a raw list of entries or a prepared AgentFallbackSettings and
        prepends the agent's own provider/model as chain index 0, the model every
        entry falls back from.
        """
        from vidbyte.agents.settings import AgentFallbackSettings as _AgentFallbackSettings

        if spec is None:
            return None
        settings = spec if isinstance(spec, _AgentFallbackSettings) else _AgentFallbackSettings(models=tuple(spec))
        return settings.to_fallback(primary=cls._primary_model(runner_config, agent_name))

    @staticmethod
    def _primary_model(runner_config: AgentRunnerConfig, agent_name: str) -> FallbackModel:
        # Chain index 0 is the agent's own runner identity; a chain needs a primary to fall back from.
        if not runner_config.provider or not runner_config.model_name:
            raise ConfigurationError(
                f"Agent {agent_name} declares a fallback chain but no provider/model_name to fall back from.",
                details={"agent": agent_name, "provider": runner_config.provider, "model_name": runner_config.model_name},
            )
        return FallbackModel(
            provider=runner_config.provider,
            model=runner_config.model_name,
            api_key=runner_config.api_key,
            temperature=runner_config.temperature,
        )

    def is_model_error(self, error: BaseException) -> bool:
        """Report whether this error is a provider-level failure a different model could survive."""
        return isinstance(error, self.fallback_on)

    def advance(self, error: BaseException, index: int) -> int | None:
        """Return the next chain index to try, or None when this error cannot be routed onward."""
        if not self.is_model_error(error) or index + 1 >= len(self.models):
            return None
        return index + 1

    def advance_after_success(self, index: int, *, cost_usd: float | None) -> int | None:
        # Returns the next chain index when a cost-budget policy's ceiling has been crossed, or None.
        if cost_usd is None or index + 1 >= len(self.models):
            return None
        ceiling = self.budget_for(index)
        if ceiling is None or cost_usd < ceiling:
            return None
        return index + 1

    def advance_after_loop_detected(self, index: int, call_contexts: Sequence["ToolCallContext"]) -> int | None:
        # Returns the next chain index when a chain-wide policy detects a stuck tool-call pattern, or None.
        if index + 1 >= len(self.models):
            return None
        if not self._is_loop_stuck(call_contexts):
            return None
        return index + 1

    def _is_loop_stuck(self, call_contexts: Sequence["ToolCallContext"]) -> bool:
        # Folds over self.policies, returning True when any policy exposing is_stuck() reports one.
        for policy in self.policies:
            is_stuck = getattr(policy, "is_stuck", None)
            if callable(is_stuck) and is_stuck(call_contexts):
                return True
        return False

    def deadline_for(self, index: int) -> float | None:
        # Returns the first policy-declared deadline for this hop, or None if no policy sets one.
        return self._first_policy_value(index, "deadline_for")

    def budget_for(self, index: int) -> float | None:
        # Returns the first policy-declared cost ceiling for this hop, or None if no policy sets one.
        return self._first_policy_value(index, "budget_for")

    def _first_policy_value(self, index: int, attr: str) -> float | None:
        # Folds over self.policies, returning the first non-None result of any policy exposing `attr`.
        for policy in self.policies:
            getter = getattr(policy, attr, None)
            if callable(getter):
                value = getter(index)
                if value is not None:
                    return value
        return None

    def transform(self, handle: RunnerHandle, provider: str, tools: Tools, messages: list[dict[str, Any]], index: int) -> FallbackTransform:
        """Rebuild the handle, provider, tool schemas, and transcript for the model at index."""
        target = self.model_at(index)
        next_handle = handle.with_runner(self.build_runner(index), target.provider)
        compatible = self.is_wire_compatible(provider, target.provider)
        return FallbackTransform(
            index=index,
            handle=next_handle,
            provider=target.provider,
            tool_schemas=self.tool_schemas_for(tools, target.provider),
            messages=list(messages) if compatible else [],
            context_reset=not compatible,
            model=target,
        )

    @staticmethod
    def tool_schemas_for(tools: Tools, provider: str) -> tuple[dict[str, Any], ...]:
        """Re-render tool declarations for a provider, mirroring AgentRuntime._resolve_tool_schemas exactly."""
        # Must stay identical to the runtime's initial derivation, or a switch silently changes the tool surface.
        return tuple(tools.provider_schemas(provider)) if len(tools) else ()

    def attempt_record(self, index: int, next_index: int, error: BaseException) -> dict[str, str]:
        """Build one credential-free record describing a single model-to-model switch."""
        return self._build_attempt_record(index, next_index, type(error).__name__)

    def policy_attempt_record(self, index: int, next_index: int, reason: str) -> dict[str, str]:
        # Builds the same record shape as attempt_record, for a switch triggered by a policy, not an exception.
        return self._build_attempt_record(index, next_index, reason)

    def _build_attempt_record(self, index: int, next_index: int, trigger: str) -> dict[str, str]:
        # Shared record shape for both the error path and the policy path.
        return {
            "from": self.model_at(index).identity(),
            "to": self.model_at(next_index).identity(),
            "error_type": trigger,
        }

    @staticmethod
    def result_metadata(attempts: Sequence[Mapping[str, str]], *, context_reset: bool) -> dict[str, Any]:
        """Summarize the switches a run made for AgentResult.metadata['fallback']."""
        return {
            "used": True,
            "attempts": [dict(attempt) for attempt in attempts],
            "final_model": attempts[-1]["to"] if attempts else None,
            "context_reset": context_reset,
        }

    def build_runner(self, index: int) -> object:
        """Build and memoize the executable runner for the model at index."""
        # Deferred: vidbyte.lib.runners transitively reaches vidbyte.lib.config, which is
        # imported early during SDK bootstrap (via lib.dataclasses.agent_descriptor); a
        # module-level import here would re-enter that chain before it finishes loading.
        from vidbyte.lib.runners import Runner

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
