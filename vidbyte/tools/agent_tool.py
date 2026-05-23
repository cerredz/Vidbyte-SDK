from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.agents.types import AgentMessage


def _build_agent_description(agent: BaseAgent, override: str | None) -> str:
    if override:
        return override
    capabilities = ", ".join(agent.capabilities) if agent.capabilities else "general purpose"
    return (
        f"Agent: {agent.name}\n"
        f"{agent.description}\n"
        f"Capabilities: {capabilities}\n"
        f"Use this tool to delegate tasks to the {agent.name} agent. "
        f"Calling this tool automatically passes the current conversation context."
    )


def serialize_context(active_prompt: str, history: list[AgentMessage]) -> str:
    """Serialize parent-agent context into a string for sub-agent consumption."""
    lines = ["<conversation_context>"]
    for msg in history:
        lines.append(f"[{msg.sender}]: {msg.content}")
    lines.append("</conversation_context>")
    if active_prompt:
        lines.extend(("", "<current_request>", active_prompt, "</current_request>"))
    return "\n".join(lines)


class AgentTool(BaseTool):
    """Wraps a BaseAgent as a zero-parameter tool for use by a parent agent.

    When invoked, the parent's live context (history + active prompt) is
    serialized and forwarded to a fresh fork of the wrapped agent.
    """

    def __init__(
        self,
        agent: BaseAgent,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        self._agent = agent
        self._name = name or agent.name
        self._description = _build_agent_description(agent, description)
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
            metadata={"agent_name": self._agent.name, "internal_agent_tool": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            if self._context_getter is not None:
                active_prompt, history = self._context_getter()
            else:
                active_prompt, history = "", []
            serialized = serialize_context(active_prompt, list(history))
            child = self._agent.fork()
            reply = await child.generate_reply(serialized)
            return ToolResult.success(
                self._name,
                reply.content,
                metadata={"agent_name": self._agent.name},
            )
        except Exception as exc:
            return ToolResult.error(
                self._name,
                str(exc),
                metadata={"agent_name": self._agent.name},
            )


__all__ = [
    "AgentTool",
    "serialize_context",
]
