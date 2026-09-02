"""Context Protocol Header

Description:
    Defines the DynamicActorTool allowing active actors to dynamically spawn sub-actors.
Purpose:
    Enables autonomous model-driven agent creation during execution to solve sub-tasks.
Architecture:
    - DynamicActorTool: Class-based SDK tool inheriting from BaseTool.
Relations:
    Located in vidbyte/tools/dynamic_actor.py. Consumed by BaseActorRuntime.
Similar Files:
    - vidbyte/tools/agent_tool.py: Agent delegation tools.
"""

from __future__ import annotations
from typing import Any
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter


class DynamicActorTool(BaseTool):
    """Allows active agent actors to dynamically spawn and register new sub-actors."""

    def __init__(self, broker: Any) -> None:
        self._broker = broker

    def spec(self) -> ToolSpec:
        """Returns the model-facing declaration for the dynamic spawn tool."""
        return ToolSpec(
            name="spawn_actor",
            description="Spawn a new specialized actor dynamically to solve a sub-task. Provide a unique actor name, a descriptive system prompt, and optionally a specific model name to run the actor with.",
            parameters=(
                ToolParameter(
                    name="actor_name",
                    type="str",
                    description="The unique name or ID of the actor to spawn (e.g., 'coder_assistant_1').",
                    required=True,
                ),
                ToolParameter(
                    name="system_prompt",
                    type="str",
                    description="Detailed system prompt or persona instructions for the spawned actor.",
                    required=True,
                ),
                ToolParameter(
                    name="model_name",
                    type="str",
                    description="Optional specialized model name to run this actor with. If not provided, falls back to worker_model or orchestrator model.",
                    required=False,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Invokes the broker spawn registry at runtime."""
        actor_name = call.arguments.get("actor_name")
        system_prompt = call.arguments.get("system_prompt")
        model_name = call.arguments.get("model_name")

        if not actor_name or not system_prompt:
            return ToolResult.error(self.name, "Both actor_name and system_prompt are required.")

        try:
            await self._broker.spawn(actor_name, system_prompt, model_name)
            return ToolResult.success(
                self.name,
                f"Successfully spawned actor '{actor_name}' with the specified system prompt.",
                metadata={"spawned_actor": actor_name},
            )
        except Exception as e:
            return ToolResult.error(self.name, f"Failed to spawn actor: {e}")
