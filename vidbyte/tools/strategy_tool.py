"""Context Protocol Header

Description:
    Wraps a BaseAgent's strategy as a callable BaseTool, bypassing the full agent lifecycle.
Purpose:
    Exposes the strategy reasoning pipeline (arun) as a tool call, using the agent's
    runner and tools without agent-level concerns (history, MCP, modality detection).
Architecture:
    - StrategyTool: BaseTool subclass that delegates execute() to agent.strategy.arun().
Relations:
    Used by BaseStrategy.as_tool(agent). Depends on vidbyte.agents.base and vidbyte.tools.base.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent


class StrategyTool(BaseTool):
    """Wraps a BaseAgent's strategy as a BaseTool, bypassing agent lifecycle."""

    def __init__(
        self,
        agent: BaseAgent,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        if agent.strategy is None:
            raise AgentExecutionError(
                f"Agent '{agent.name}' has no strategy. "
                "StrategyTool requires an agent with a strategy attached."
            )
        self._agent = agent
        self._strategy = agent.strategy
        self._name = name or f"{agent.name}_strategy"
        strategy_description = getattr(agent.strategy, "description", "") or ""
        self._description = (
            description
            or strategy_description
            or f"Run the {agent.strategy.strategy_name} strategy."
        )
        self._spec = ToolSpec(
            name=self._name,
            description=self._description,
            parameters=(
                ToolParameter(
                    name="prompt",
                    type="string",
                    description="The prompt to run through the strategy.",
                    required=True,
                ),
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The prompt to run through the strategy."},
                },
                "required": ["prompt"],
            },
            permission=ToolPermission.SAFE,
            metadata={
                "source": "strategy",
                "strategy_name": agent.strategy.strategy_name,
                "agent_name": agent.name,
            },
        )

    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, call: ToolCall) -> ToolResult:
        prompt = str(call.arguments["prompt"])

        from vidbyte.agents.base import ConfiguredAgentRunner

        runner = self._agent._runner_for_modality(ModelModality.TEXT)
        if runner is None or isinstance(runner, ConfiguredAgentRunner):
            return ToolResult.failure(
                self._name,
                f"StrategyTool '{self._name}' requires an executable runner. "
                f"Agent '{self._agent.name}' has no real runner configured.",
                metadata={"error_type": "no_runner", "agent_name": self._agent.name},
            )

        try:
            result = await self._strategy.arun(
                prompt,
                runner=runner,
                tools=self._agent._agent_tool_items,
            )
            return ToolResult.success(
                self._name,
                result.output,
                metadata={
                    "strategy_name": result.strategy_name,
                    "agent_name": self._agent.name,
                },
            )
        except Exception as exc:
            return ToolResult.failure(
                self._name,
                str(exc),
                metadata={
                    "strategy_name": self._strategy.strategy_name,
                    "error_type": type(exc).__name__,
                },
            )


__all__ = ["StrategyTool"]
