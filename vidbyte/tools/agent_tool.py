from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.agents.types import AgentMessage


class AgentTool(BaseTool):
    """Wraps a BaseAgent as a zero-parameter tool for use by a parent agent.

    When invoked, the parent's live context (history + active prompt) is
    serialized and forwarded to a fresh fork of the wrapped agent.
    """

    def __init__(self, agent: BaseAgent) -> None:
        self._agent = agent
        self._name = agent.agent_metadata.name
        self._description = self._build_agent_description()
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
            metadata={"agent_name": self._agent.agent_metadata.name, "internal_agent_tool": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            if self._context_getter is not None:
                active_prompt, history = self._context_getter()
            else:
                active_prompt, history = "", []
            serialized = self._serialize_context(active_prompt, list(history))
            child = self._agent.fork()
            reply = await child.generate_reply(serialized)
            return ToolResult.success(
                self._name,
                reply.content,
                metadata={"agent_name": self._agent.agent_metadata.name},
            )
        except Exception as exc:
            return ToolResult.error(
                self._name,
                str(exc),
                metadata={"agent_name": self._agent.agent_metadata.name},
            )

    def _build_agent_description(self) -> str:
        meta = self._agent.agent_metadata
        return (
            f"Agent: {meta.name}\n"
            f"Description: {meta.description}\n"
            f"Use Cases: {meta.use_cases}\n"
            f"Use this tool to delegate tasks to the {meta.name} agent. "
            f"Calling this tool automatically passes the current conversation context."
        )

    @staticmethod
    def _serialize_context(active_prompt: str, history: list[AgentMessage]) -> str:
        """Serialize parent-agent context into a string for sub-agent consumption."""
        lines = ["<conversation_context>"]
        for msg in history:
            lines.append(f"[{msg.sender}]: {msg.content}")
        lines.append("</conversation_context>")
        if active_prompt:
            lines.extend(("", "<current_request>", active_prompt, "</current_request>"))
        return "\n".join(lines)


__all__ = ["AgentTool"]
