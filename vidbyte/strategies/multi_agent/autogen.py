from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.registry import AgentRegistry
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.multi_agent.base import BaseMultiAgentStrategy
from vidbyte.strategies.types import StrategyContext, StrategyResult


class AutoGenConversationStrategy(BaseMultiAgentStrategy):
    """Local AutoGen-style message-passing strategy."""

    name = "multi_agent.autogen"

    def __init__(
        self,
        *,
        agents: Sequence[BaseAgent],
        initial_agent: str,
        transition_policy: Callable[[Sequence[AgentMessage], AgentRegistry], str | None],
        max_turns: int = 8,
        termination_predicate: Callable[[AgentMessage], bool] | None = None,
    ) -> None:
        super().__init__(max_calls=max_turns)
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1.")
        self.registry = AgentRegistry()
        for agent in agents:
            self.registry.register(agent)
        self.initial_agent = initial_agent
        self.transition_policy = transition_policy
        self.max_turns = max_turns
        self.termination_predicate = termination_predicate

    async def arun(
        self,
        prompt: str,
        *,
        runner: object | None = None,
        context: StrategyContext | None = None,
        tools: Sequence[object] = (),
        **options: Any,
    ) -> StrategyResult:
        self._reset_calls()
        transcript: list[AgentMessage] = []
        next_agent_name: str | None = self.initial_agent
        current_prompt = prompt
        stopped_by = "policy"
        while next_agent_name is not None and len(transcript) < self.max_turns:
            agent = self.registry.get(next_agent_name)
            reply = await self._run_agent(
                agent,
                current_prompt,
                context=context,
                history=tuple(transcript),
                recipient="conversation",
                **options,
            )
            transcript.append(reply)
            if self.termination_predicate and self.termination_predicate(reply):
                stopped_by = "termination_predicate"
                break
            next_agent_name = self.transition_policy(tuple(transcript), self.registry)
            current_prompt = reply.content
        else:
            if len(transcript) >= self.max_turns:
                stopped_by = "max_turns"
        if not transcript:
            raise StrategyExecutionError("Conversation produced no messages.")
        return StrategyResult(
            output=transcript[-1].content,
            strategy_name=self.name,
            metadata={
                "stopped_by": stopped_by,
                "turns": len(transcript),
                "transcript": [_message_dict(message) for message in transcript],
            },
        )


def _message_dict(message: AgentMessage) -> dict[str, object]:
    return {
        "sender": message.sender,
        "recipient": message.recipient,
        "content": message.content,
        "metadata": dict(message.metadata),
    }
