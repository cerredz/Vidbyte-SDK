"""FILE: vidbyte/agents/reasoning_effort.py

PURPOSE: Defines AgentReasoningEffortGuard, the construction refusal behind BaseAgent's reasoning_effort: an agent that sets an effort is refused before any call when its mode cannot send one, when any model in its chain has no documented form for the value, or when its context-window algorithm calls models through runners it builds itself.
ROLE IN CODEBASE: Called twice by BaseAgent.__init__ (vidbyte/agents/base.py): refuse_unsupported right after the spend-cap refusal, and refuse_algorithm_models right after the algorithm is resolved. It reads the agent's AgentRunnerConfig, AgentFallback and ContextWindowAlgorithm and asks ReasoningEffortRegistry (vidbyte/lib/registries/reasoning_effort.py) for each model's reason; it never builds a runner or sends anything.
ARCHITECTURE NOTE: The chain is fallback.models when the agent has a fallback (index 0 is the primary), else the primary alone, and each entry is read through Runner._normalize_provider_and_model, exactly as its runner will read it. Reasons follow the chain order and are de-duplicated in that order, so a gateway mode is named once and before any model's capability reason. Every hop is checked, because a hop is only reached after the hops in front of it have failed, which is too late to refuse. The algorithm check runs second, so a chain reason always outranks the algorithm text.
FUNCTION INVENTORY: AgentReasoningEffortGuard.refuse_unsupported (raises ConfigurationError with the agent-level text, or returns when the effort is unset or every hop can send it); AgentReasoningEffortGuard.refuse_algorithm_models (raises ConfigurationError with the algorithm text when the multi_provider_agentic_grader, an independent_critic with a reviewer, or a prosecutor_defender_judge with a stage model would build its own runners, or returns).
COMMON MODIFICATION PATTERNS: A new reason belongs in ReasoningEffortRegistry.refusal, so TextModelConfig, JevAgentSettings and this guard all give it; this file only gathers the reasons across the chain and words the agent-level sentence. A new context-window algorithm that builds its own runners is one more entry in refuse_algorithm_models, keyed by its ContextWindowAlgorithm field name.
WHAT NOT TO DO IN THIS FILE: 1. Do not send a request or build a runner here; the refusal must cost nothing. 2. Do not mutate the runner config, the fallback chain or the algorithm. 3. Do not quote keys or prompts; the text names the agent, providers, models, values, modes and algorithm keys only. 4. Do not name an algorithm by ContextWindowAlgorithm.name, which the user chooses; name the fixed key of its sub-algorithm.
KNOWN EDGE CASES: An agent that does not name both a provider and a model_name (on any hop) is refused with the identity text, because its effort cannot be checked against a model. A fork child is refused by its own construction, so a fork to a model that cannot take the parent's effort fails at fork time. A slug such as 'anthropic/claude-sonnet-5' with no provider is checked against the row its runner resolves. At most one context-window algorithm is set, so the algorithm text names one key; the critic's reviewer pair and each debate stage's provider and model pair are all-or-nothing, so a half-set pair fails in its own record first. An algorithm assigned after construction is not re-checked.
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
    from vidbyte.context.window import ContextWindowAlgorithm
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

    @staticmethod
    def refuse_algorithm_models(*, agent_name: str, runner_config: AgentRunnerConfig, algorithm: ContextWindowAlgorithm) -> None:
        """Raise ConfigurationError when the agent's context-window algorithm calls models through runners it builds itself."""
        # @intent algorithm-built-runners-cannot-carry-the-effort
        # These algorithms build their runners with
        # ModalityDetector.create_runner, which is never given the
        # effort, and the preset grader picks its models at run time,
        # so the effort could be neither sent nor checked per model.
        effort = runner_config.reasoning_effort
        if effort is None:
            return
        # Find the one algorithm here, if any, that builds its own
        # runners, from its fields and never from the name it was given.
        critic = algorithm.independent_critic
        debate = algorithm.prosecutor_defender_judge
        stages = () if debate is None else (debate.prosecutor, debate.defender, debate.judge)
        builds_own_runners = {
            "multi_provider_agentic_grader": algorithm.multi_provider_agentic_grader is not None,
            "independent_critic": critic is not None and critic.reviewer_provider is not None,
            "prosecutor_defender_judge": any(stage.provider is not None and stage.model is not None for stage in stages),
        }
        key = next((name for name, builds in builds_own_runners.items() if builds), None)
        # An algorithm that runs only on the agent's own model sends the
        # effort through the agent's runner, so it is let through.
        if key is None:
            return
        raise ConfigurationError(
            f"Agent {agent_name} sets reasoning_effort, but its {key} algorithm calls models through runners it builds itself, which never send the effort; unset reasoning_effort, or configure an algorithm that runs only on the agent's own model.",
            details={"agent": agent_name, "field": "reasoning_effort", "reasoning_effort": effort.value, "algorithm": key},
        )


__all__ = ["AgentReasoningEffortGuard"]
