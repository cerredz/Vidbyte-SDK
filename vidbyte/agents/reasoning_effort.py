"""FILE: vidbyte/agents/reasoning_effort.py

PURPOSE: Defines AgentReasoningEffortGuard, the construction refusal behind BaseAgent's reasoning_effort: an agent that sets an effort is refused before any call when its mode cannot send one, or when any model in its chain has no documented form for the value.
ROLE IN CODEBASE: Called by BaseAgent.__init__ (vidbyte/agents/base.py) right after the spend-cap refusal. It reads the agent's AgentRunnerConfig and AgentFallback and asks ReasoningEffortRegistry (vidbyte/lib/registries/reasoning_effort.py) for each model's reason; it never builds a runner or sends anything.
ARCHITECTURE NOTE: The chain is fallback.models when the agent has a fallback (index 0 is the primary), else the primary alone, and each entry is read through Runner._normalize_provider_and_model, exactly as its runner will read it. Reasons follow the chain order and are de-duplicated in that order, so a gateway mode is named once and before any model's capability reason. Every hop is checked, because a hop is only reached after the hops in front of it have failed, which is too late to refuse.
FUNCTION INVENTORY: AgentReasoningEffortGuard.refuse_unsupported (raises ConfigurationError with the agent-level text, or returns when the effort is unset or every hop can send it).
COMMON MODIFICATION PATTERNS: A new reason belongs in ReasoningEffortRegistry.refusal, so TextModelConfig, JevAgentSettings and this guard all give it; this file only gathers the reasons across the chain and words the agent-level sentence.
WHAT NOT TO DO IN THIS FILE: 1. Do not send a request or build a runner here; the refusal must cost nothing. 2. Do not mutate the runner config or the fallback chain. 3. Do not quote keys or prompts; the text names the agent, providers, models, values and modes only.
KNOWN EDGE CASES: An agent that does not name both a provider and a model_name (on any hop) is refused with the identity text, because its effort cannot be checked against a model. A fork child is refused by its own construction, so a fork to a model that cannot take the parent's effort fails at fork time. A slug such as 'anthropic/claude-sonnet-5' with no provider is checked against the row its runner resolves.
RELATED DOCS: vidbyte/agents/README.md (section Reasoning Effort); docs/spec/agent-reasoning-effort/spec.md
TESTS: tests/features/agent_reasoning_effort
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.reasoning_effort import ReasoningEffortRegistry
from vidbyte.lib.runners import Runner

if TYPE_CHECKING:
    from vidbyte.agents.fallback import AgentFallback
    from vidbyte.lib.dataclasses.agents import AgentRunnerConfig


class AgentReasoningEffortGuard:
    """Construction refusal for BaseAgent's reasoning_effort, checked across the whole fallback chain."""

    @staticmethod
    def refuse_unsupported(*, agent_name: str, runner_config: AgentRunnerConfig, fallback: AgentFallback | None) -> None:
        """Raise ConfigurationError when the agent's mode or any model in its chain cannot send its reasoning effort."""
        # @intent reasoning-effort-is-refused-before-any-call
        # A bad primary in front of a good fallback would be found only
        # after a paid failed call, and a bad fallback only after the
        # primary failed, so every hop is checked here, before any
        # request or spend.
        effort = runner_config.reasoning_effort
        if effort is None:
            return
        details = {"agent": agent_name, "field": "reasoning_effort", "reasoning_effort": effort.value}
        # Read each model in the chain the way its runner will read it:
        # the fallback chain when there is one, else the primary alone.
        entries = [(entry.provider, entry.model) for entry in fallback.models] if fallback is not None else [(runner_config.provider, runner_config.model_name)]
        pairs = [Runner._normalize_provider_and_model(provider, model)[:2] for provider, model in entries]
        named = [(provider, model) for provider, model in pairs if provider is not None and model is not None]
        # Without both a provider and a model there is no row to check.
        if len(named) < len(pairs):
            raise ConfigurationError(
                f"Agent {agent_name} sets reasoning_effort, but it does not name both a provider and a model_name, so the effort cannot be checked against a model.",
                details=details,
            )
        # Gather each hop's reason in chain order and name each once, so
        # a gateway mode appears a single time, before any model reason.
        reasons = [ReasoningEffortRegistry.refusal(provider=provider, model=model, effort=effort, mode=runner_config.model_mode) for provider, model in named]
        unique = list(dict.fromkeys(reason for reason in reasons if reason is not None))
        if unique:
            raise ConfigurationError(f"Agent {agent_name} sets reasoning_effort, but {'; '.join(unique)}.", details=details)


__all__ = ["AgentReasoningEffortGuard"]
