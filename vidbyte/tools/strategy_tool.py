from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import AgentExecutionError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.agents.types import AgentMessage


def _serialize_context(active_prompt: str, history: list[AgentMessage]) -> str:
    """Serialize parent-agent context into a string for sub-agent consumption."""
    lines = ["<conversation_context>"]
    for msg in history:
        lines.append(f"[{msg.sender}]: {msg.content}")
    lines.append("</conversation_context>")
    if active_prompt:
        lines.extend(("", "<current_request>", active_prompt, "</current_request>"))
    return "\n".join(lines)


class StrategyTool(BaseTool):
    """Wraps an agent's strategy as a zero-parameter tool.

    Raises AgentExecutionError at construction when the agent has no strategy.
    When invoked, serializes the parent context and calls strategy.arun()
    directly with the serialized prompt.
    """

    def __init__(
        self,
        agent: BaseAgent,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        if agent.strategy is None:
            raise AgentExecutionError(
                f"Agent '{agent.name}' has no strategy; cannot create StrategyTool."
            )
        self._agent = agent
        self._name = name or f"{agent.name}_strategy"
        self._description = description or agent.strategy.description or agent.description
        self._context_getter: Callable[[], tuple[str, list[Any]]] | None = None

    def bind_context_getter(
        self,
        getter: Callable[[], tuple[str, list[Any]]],
    ) -> None:
        """Bind a callable that returns (active_prompt, history) at call time."""
        self._context_getter = getter

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._name,
            description=self._description,
            parameters=(),
            permission=ToolPermission.SAFE,
            metadata={
                "strategy_name": self._agent.strategy.strategy_name,  # type: ignore[union-attr]
                "agent_name": self._agent.name,
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        from vidbyte.agents.base import ConfiguredAgentRunner

        runner = self._agent.runner
        if runner is None or isinstance(runner, ConfiguredAgentRunner):
            return ToolResult.error(
                self._name,
                "No real runner configured for this agent's strategy tool.",
                metadata={
                    "agent_name": self._agent.name,
                    "strategy_name": self._agent.strategy.strategy_name,  # type: ignore[union-attr]
                },
            )
        try:
            if self._context_getter is not None:
                active_prompt, history = self._context_getter()
            else:
                active_prompt, history = "", []
            serialized = _serialize_context(active_prompt, list(history))
            strategy = self._agent.strategy  # type: ignore[union-attr]
            result = await strategy.arun(
                serialized,
                runner=runner,
                tools=self._agent._agent_tool_items,
            )
            return ToolResult.success(
                self._name,
                result.output,
                metadata={
                    "agent_name": self._agent.name,
                    "strategy_name": result.strategy_name,
                },
            )
        except Exception as exc:
            return ToolResult.error(
                self._name,
                str(exc),
                metadata={
                    "agent_name": self._agent.name,
                    "strategy_name": self._agent.strategy.strategy_name,  # type: ignore[union-attr]
                },
            )


__all__ = ["StrategyTool"]
