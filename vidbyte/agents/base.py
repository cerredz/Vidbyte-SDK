from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vidbyte.agents.types import AgentCard, AgentMessage, AgentRole
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyContext


class BaseAgent:
    """Reusable actor combining a strategy, runner, role, and tools."""

    def __init__(
        self,
        *,
        name: str,
        strategy: BaseStrategy,
        runner: object | None = None,
        tools: Sequence[object] = (),
        role: AgentRole = "worker",
        description: str = "",
        capabilities: Sequence[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not name:
            raise AgentExecutionError("Agent name cannot be empty.")
        if strategy is None:
            raise AgentExecutionError("Agent strategy is required.")
        self.name = name
        self.strategy = strategy
        self.runner = runner
        self.tools = tuple(tools)
        self.role = role
        self.description = description or "General purpose agent."
        self.capabilities = tuple(capabilities)
        self.metadata = dict(metadata or {})
        self.history: list[AgentMessage] = []

    def card(self) -> AgentCard:
        return AgentCard(
            name=self.name,
            role=self.role,
            description=self.description,
            capabilities=self.capabilities,
            tool_names=tuple(_tool_name(tool) for tool in self.tools),
            metadata=dict(self.metadata),
        )

    async def receive(self, message: AgentMessage) -> None:
        self.history.append(message)

    async def generate_reply(
        self,
        message: str,
        *,
        context: StrategyContext | None = None,
        history: Sequence[AgentMessage] = (),
        recipient: str = "orchestrator",
        **options: Any,
    ) -> AgentMessage:
        merged_history = tuple(history) + tuple(self.history)
        metadata = dict(context.metadata if context else {})
        metadata.update(self.metadata)
        agent_context = StrategyContext(
            system_prompt=context.system_prompt if context else None,
            agent_name=self.name,
            role=self.role,
            history=merged_history,
            metadata=metadata,
        )
        try:
            result = await self.strategy.arun(
                message,
                runner=self.runner,
                context=agent_context,
                tools=self.tools,
                **options,
            )
        except Exception as exc:
            raise AgentExecutionError(
                f"Agent '{self.name}' failed to generate a reply.",
                details={"agent": self.name, "role": self.role, "error_type": type(exc).__name__},
            ) from exc
        reply = AgentMessage(
            sender=self.name,
            recipient=recipient,
            content=result.output,
            metadata={"strategy": result.strategy_name, **dict(result.metadata)},
        )
        self.history.append(reply)
        return reply


def _tool_name(tool: object) -> str:
    spec = getattr(tool, "spec", None)
    if callable(spec):
        try:
            tool_spec = spec()
        except Exception:
            return tool.__class__.__name__
        name = getattr(tool_spec, "name", None)
        if name:
            return str(name)
    return tool.__class__.__name__
