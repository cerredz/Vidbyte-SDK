"""Context Protocol Header

Description:
    Dynamic multi-agent orchestration strategy with pluggable next-agent selection policies.
Purpose:
    Enables agents to evolve and coordinate dynamically over multiple conversational turns.
Architecture:
    - OrchestrationPolicy: Protocol defining the select_next interface.
    - HeuristicPolicy: Cycles through workers and service/evaluator agents.
    - EvolvingOrchestrationStrategy: Integrates policies with AgentRegistry to run evolving agent loops.
Relations:
    Located in vidbyte/strategies/multi_agent/evolving.py. Utilized by multi-agent workflows.
Similar Files:
    - vidbyte/strategies/multi_agent/consensus.py: Consensus strategy.
    - vidbyte/strategies/multi_agent/vmao.py: Multi-agent orchestration.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.registries import AgentRegistry
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.multi_agent.base import BaseMultiAgentStrategy
from vidbyte.strategies.types import StrategyContext, StrategyResult


class OrchestrationPolicy(Protocol):
    def select_next(self, *, prompt: str, transcript: Sequence[AgentMessage], registry: AgentRegistry) -> str | None:
        """Select the next agent name, or None to stop."""


class HeuristicPolicy:
    """Deterministic policy that cycles workers once, then evaluator/service agents."""

    def select_next(self, *, prompt: str, transcript: Sequence[AgentMessage], registry: AgentRegistry) -> str | None:
        used = {message.sender for message in transcript}
        for agent in registry.find(metadata={"role": "worker"}):
            if agent.name not in used:
                return agent.name
        for role in ("service", "evaluator", "support"):
            for agent in registry.find(metadata={"role": role}):
                if agent.name not in used:
                    return agent.name
        return None


class EvolvingOrchestrationStrategy(BaseMultiAgentStrategy):
    """Dynamic next-agent selection with a pluggable inference-time policy."""

    name = "multi_agent.evolving"

    def __init__(self, *, agents: Sequence[BaseAgent], policy: OrchestrationPolicy | None = None, max_turns: int = 8, exploration_width: int = 1) -> None:
        super().__init__(max_calls=max_turns)
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1.")
        if exploration_width < 1:
            raise ValueError("exploration_width must be at least 1.")
        self.registry = AgentRegistry()
        for agent in agents:
            self.registry.register(agent)
        self.policy = policy or HeuristicPolicy()
        self.max_turns = max_turns
        self.exploration_width = exploration_width

    async def arun(self, prompt: str, *, runner: object | None = None, context: StrategyContext | None = None, tools: Sequence[object] = (), **options: object) -> StrategyResult:
        self._reset_calls()
        transcript: list[AgentMessage] = []
        current_prompt = prompt
        stopped_by = "policy"
        for _ in range(self.max_turns):
            next_name = self.policy.select_next(
                prompt=prompt,
                transcript=tuple(transcript),
                registry=self.registry,
            )
            if next_name is None:
                break
            agent = self.registry.get(next_name)
            reply = await self._run_agent(
                agent,
                current_prompt,
                context=context,
                history=tuple(transcript),
                recipient="evolving",
                **options,
            )
            transcript.append(reply)
            current_prompt = reply.content
        else:
            stopped_by = "max_turns"
        if not transcript:
            raise StrategyExecutionError("Evolving orchestration produced no messages.")
        return StrategyResult(
            output=transcript[-1].content,
            strategy_name=self.name,
            metadata={
                "stopped_by": stopped_by,
                "turns": len(transcript),
                "exploration_width": self.exploration_width,
                "transcript": [
                    {
                        "sender": message.sender,
                        "recipient": message.recipient,
                        "content": message.content,
                        "message_type": message.message_type,
                        "metadata": dict(message.metadata),
                    }
                    for message in transcript
                ],
            },
        )
