"""Context Protocol Header

Description:
    Wraps a BaseAgent as a callable BaseTool for registration in another agent's Tools catalog.
Purpose:
    Enables agent-as-tool composition so any configured agent can be invoked through the
    standard tool-call flow by a parent agent or harness.
Architecture:
    - AgentTool: BaseTool subclass that delegates execute() to agent.fork().generate_reply().
Relations:
    Used by BaseAgent.as_tool(). Depends on vidbyte.agents.base and vidbyte.tools.base.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent


class AgentTool(BaseTool):
    """Wraps a BaseAgent as a BaseTool using the full agent lifecycle."""

    def __init__(
        self,
        agent: BaseAgent,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        self._agent = agent
        self._name = name or agent.name
        self._description = description or agent.description or f"Agent: {agent.name}"
        self._spec = ToolSpec(
            name=self._name,
            description=self._description,
            parameters=(
                ToolParameter(
                    name="message",
                    type="string",
                    description="The message to send to the agent.",
                    required=True,
                ),
                ToolParameter(
                    name="recipient",
                    type="string",
                    description="The intended recipient label for this message.",
                    required=False,
                    default="orchestrator",
                ),
                ToolParameter(
                    name="modality",
                    type="string",
                    description="The modality to use (text, image, video, or auto).",
                    required=False,
                    default="auto",
                ),
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The message to send to the agent."},
                    "recipient": {"type": "string", "description": "The intended recipient label.", "default": "orchestrator"},
                    "modality": {"type": "string", "description": "The modality to use.", "default": "auto"},
                },
                "required": ["message"],
            },
            permission=ToolPermission.SAFE,
            metadata={"source": "agent", "agent_name": agent.name},
        )

    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, call: ToolCall) -> ToolResult:
        message = str(call.arguments["message"])
        recipient = str(call.arguments.get("recipient", "orchestrator"))
        modality_raw = call.arguments.get("modality", "auto")
        modality: Any = None if (not modality_raw or modality_raw == "auto") else modality_raw

        try:
            reply = await self._agent.fork().generate_reply(
                message,
                recipient=recipient,
                modality=modality,
            )
            return ToolResult.success(
                self._name,
                reply.content,
                metadata={
                    "agent_name": self._agent.name,
                    "sender": reply.sender,
                    "recipient": reply.recipient,
                },
            )
        except Exception as exc:
            return ToolResult.failure(
                self._name,
                str(exc),
                metadata={"agent_name": self._agent.name, "error_type": type(exc).__name__},
            )


__all__ = ["AgentTool"]
