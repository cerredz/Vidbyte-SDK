from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vidbyte.strategies.base import BaseStrategy


class StrategyClient:
    """Namespace client for strategy factories."""

    def consensus(
        self,
        strategies: Sequence[BaseStrategy],
        *,
        evaluator_agent: object | None = None,
        evaluator_strategy: BaseStrategy | None = None,
        **options: Any,
    ) -> BaseStrategy:
        from vidbyte.strategies.multi_agent.consensus import MultiAgentConsensusStrategy

        return MultiAgentConsensusStrategy(
            strategies=strategies,
            evaluator_agent=evaluator_agent,
            evaluator_strategy=evaluator_strategy,
            **options,
        )

    def autogen(self, **options: Any) -> BaseStrategy:
        from vidbyte.strategies.multi_agent.autogen import AutoGenConversationStrategy

        return AutoGenConversationStrategy(**options)

    def vmao(self, **options: Any) -> BaseStrategy:
        from vidbyte.strategies.multi_agent.vmao import VerifiedMultiAgentOrchestrationStrategy

        return VerifiedMultiAgentOrchestrationStrategy(**options)

    def economic_gate(self, **options: Any) -> BaseStrategy:
        from vidbyte.strategies.multi_agent.economic_gate import EconomicGateStrategy

        return EconomicGateStrategy(**options)

    def evolving(self, **options: Any) -> BaseStrategy:
        from vidbyte.strategies.multi_agent.evolving import EvolvingOrchestrationStrategy

        return EvolvingOrchestrationStrategy(**options)

    @property
    def multi_agent(self) -> "StrategyClient":
        return self
