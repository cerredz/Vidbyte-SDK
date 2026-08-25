"""Context Protocol Header

FILE: vidbyte/agents/fallback/chain.py
PURPOSE: Routes one in-flight agent run through an ordered, already-validated
         model chain and rebuilds provider-derived state for each switch.
ROLE IN CODEBASE: AgentFallbackSettings creates the chain; AgentRuntime submits
                  validated transition requests; this module owns advance,
                  exhaustion, runner caching, and provider wire-format transforms.
ARCHITECTURE NOTE: AgentFallback accepts only AgentFallbackConfig. The public
                    fallback_transition() method is the single state-transition
                    boundary for both provider errors and proactive policies.
FUNCTION INVENTORY:
    - from_spec: resolves public fallback settings into the internal chain.
    - advance/advance_after_success: select the next model for error/policy triggers.
    - fallback_transition: records and applies one validated transition.
    - transform: rebuilds runner, provider schemas, transcript, and reset state.
    - build_runner/model_at: lazily cache and safely access chain entries.
    - result_metadata/attempt_record: produce credential-free audit data.
COMMON MODIFICATION PATTERNS: Put new transition causes behind
    FallbackTransitionRequest and preserve the shared attempt record shape.
WHAT NOT TO DO: Do not duplicate request validation in AgentRuntime or bypass
    AgentFallbackConfig with a parallel constructor signature.
KNOWN EDGE CASES: Cost transitions are proactive and do not manufacture an
    exception; terminal error transitions raise AllModelsFailedError only after
    a prior switch has been recorded.
COMMON ERRORS: FallbackConfigurationError, FallbackTransitionError, and
    AllModelsFailedError.
TEST FILES: Existing fallback/runtime tests and scripts/run_ci.py.
CONCURRENCY MODEL: Runner cache belongs to one AgentFallback instance and is
    populated lazily; transition history belongs to one active run.
RELATED DOCS: docs/design/agent-fallback-policies.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.agents import (
    AgentFallbackConfig,
    FallbackModel,
    FallbackTransform,
    FallbackTransition,
    FallbackTransitionRequest,
)
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.errors import (
    AllModelsFailedError,
    ConfigurationError,
    FallbackConfigurationError,
    FallbackTransitionError,
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

    def __init__(self, config: AgentFallbackConfig) -> None:
        # Stores the validated chain (index 0 is the primary) and caches runners lazily by chain index.
        if not isinstance(config, AgentFallbackConfig):
            raise FallbackConfigurationError("AgentFallback requires an AgentFallbackConfig instance.")
        self.models = config.models
        self.fallback_on = config.fallback_on
        self.policies = config.policies
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
        from vidbyte.agents.settings import (
            AgentFallbackSettings as _AgentFallbackSettings,
        )

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

    # @intent fallback-transition-boundary
    # A fallback switch is a domain state transition: it changes the provider,
    # model, tool wire format, visible transcript, and the durable audit record
    # for the run. The transition must therefore be accepted only after the
    # shared request contract has checked the current index, provider catalog,
    # message shape, and history integrity.
    #
    # Error-triggered switches preserve the existing provider-error semantics;
    # cost-triggered switches are proactive and must not manufacture an error.
    # Both paths append the same credential-free attempt shape before rebuilding
    # state so metadata, traces, and exhaustion errors describe the same event.
    # A runtime rewrite that performs these checks ad hoc can switch with a stale
    # provider or malformed transcript, causing provider rejection, lost context,
    # or an audit record that no longer matches the model actually used.
    def fallback_transition(self, request: FallbackTransitionRequest) -> FallbackTransition | None:
        """Apply one validated transition request, or return None when it cannot advance."""
        if not isinstance(request, FallbackTransitionRequest):
            raise FallbackTransitionError("AgentFallback.fallback_transition requires a FallbackTransitionRequest.")
        if request.chain_length != len(self.models):
            raise FallbackTransitionError(
                "FallbackTransitionRequest.chain_length does not match the configured fallback chain.",
                details={"request_chain_length": request.chain_length, "actual_chain_length": len(self.models)},
            )
        next_index = self._next_transition_index(request)
        if next_index is None:
            self._raise_exhausted(request)
            return None
        attempt = self._record_transition(request, next_index)
        transform = self.transform(request.handle, request.provider, request.tools, list(request.messages), next_index)
        return FallbackTransition(transform=transform, attempt=attempt)

    def _next_transition_index(self, request: FallbackTransitionRequest) -> int | None:
        if request.error is not None:
            return self.advance(request.error, request.index)
        return self.advance_after_success(request.index, cost_usd=request.cost_usd)

    def _record_transition(self, request: FallbackTransitionRequest, next_index: int) -> dict[str, str]:
        if request.error is not None:
            request.errors.append(request.error)
            attempt = self.attempt_record(request.index, next_index, request.error)
        else:
            attempt = self.policy_attempt_record(request.index, next_index, request.reason or "policy_triggered")
        request.attempts.append(attempt)
        return attempt

    def _raise_exhausted(self, request: FallbackTransitionRequest) -> None:
        if request.error is None or not self.is_model_error(request.error) or not request.attempts:
            return
        causes = [*request.errors, request.error]
        raise AllModelsFailedError(
            f"Agent '{request.agent_name}' exhausted its fallback chain after {len(request.attempts)} model switch(es).",
            attempts=request.attempts,
            errors=causes,
        ) from causes[0]

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
            raise FallbackConfigurationError(f"Fallback chain index {index} is out of range for a chain of {len(self.models)}.")
        return self.models[index]

    def __len__(self) -> int:
        """Return the chain length, including the primary model."""
        return len(self.models)

    def __repr__(self) -> str:
        """Return the ordered chain identities without exposing any credentials."""
        chain = " -> ".join(model.identity() for model in self.models)
        return f"AgentFallback({chain})"


__all__ = ["DEFAULT_FALLBACK_ERRORS", "AgentFallback", "FallbackTransform"]
