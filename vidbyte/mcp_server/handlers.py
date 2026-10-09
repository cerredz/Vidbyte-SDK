"""Context Protocol Header

Description:
    Implements studio tool logic that bridges MCP tool calls into real SDK operations.
Purpose:
    Each handler class wraps one SDK capability (agent listing, tool listing, etc.)
    as a standard BaseTool that the MCP server can register and dispatch.
Architecture:
    - StudioToolRegistry: Collects and dispatches all studio tools.
    - Each tool class (StudioAgentsListTool, etc.) extends BaseTool.
    - Tools receive their dependencies (agent map, tool sequence, etc.) on construction.
Relations:
    Used by vidbyte.mcp_server.server. Depends on vidbyte.mcp_server.schema.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentCard
from vidbyte.mcp_server.schema import McpSchema
from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class StudioToolRegistry:
    """Collects and dispatches all studio management tools."""

    def __init__(
        self,
        *,
        agents: Mapping[str, BaseAgent] | None = None,
        tools: Sequence[BaseTool] = (),
        strategy_names: Sequence[str] = (),
        pipeline_names: Sequence[str] = (),
        prompt_families: Mapping[str, Sequence[str]] | None = None,
        prompt_content: Mapping[str, str] | None = None,
    ) -> None:
        self._agents = dict(agents or {})
        self._tools = tuple(tools)
        self._strategy_names = tuple(strategy_names)
        self._pipeline_names = tuple(pipeline_names)
        self._prompt_families = dict(prompt_families or {})
        self._prompt_content = dict(prompt_content or {})

        self._tool_map: dict[str, BaseTool] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        builtins: list[BaseTool] = [
            StudioAgentsListTool(self._agents),
            StudioAgentsRunTool(self._agents),
            StudioToolsListTool(self._tools),
            StudioStrategiesListTool(self._strategy_names),
            StudioStrategiesRunTool(self._strategy_names),
            StudioPromptsListTool(self._prompt_families),
            StudioPromptsGetTool(self._prompt_content),
            StudioPipelinesListTool(self._pipeline_names),
        ]
        for tool in builtins:
            self._tool_map[tool.spec().name] = tool
        for tool in self._tools:
            self._tool_map[tool.spec().name] = tool

    def all_tools(self) -> tuple[BaseTool, ...]:
        return tuple(self._tool_map.values())

    def tool_specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec() for tool in self._tool_map.values())

    def find_tool(self, name: str) -> BaseTool | None:
        return self._tool_map.get(name)

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.find_tool(name)
        if tool is None:
            return ToolResult.error(name, f"Unknown tool: {name}")
        return await tool.execute(ToolCall(name, arguments))


class StudioAgentsListTool(BaseTool):
    def __init__(self, agents: Mapping[str, BaseAgent]) -> None:
        self._agents = agents

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="studio.agents.list",
            description="List all registered agents and their capabilities.",
            parameters=(
                ToolParameter("filter_name", "string", "An optional text filter applied to the registered agent names. When it is provided, only agents whose name contains this text are listed, which keeps the response small on studios with many agents. Leave it out to list every registered agent. The match is a plain substring check on the agent name and does not change which agents can be run.", required=False),
            ),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "studio"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        filter_name = (call.arguments.get("filter_name") or "").strip()
        cards: list[dict[str, Any]] = []
        for agent_name, agent in self._agents.items():
            if filter_name and filter_name.lower() not in agent_name.lower():
                continue
            card: AgentCard = agent.card()
            cards.append({
                "name": card.name,
                "description": card.description,
                "capabilities": list(card.capabilities),
                "tool_names": list(card.tool_names),
                "mcp_tool_names": list(card.mcp_tool_names),
            })
        return ToolResult.success("studio.agents.list", json.dumps(cards, indent=2))


class StudioAgentsRunTool(BaseTool):
    def __init__(self, agents: Mapping[str, BaseAgent]) -> None:
        self._agents = agents

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="studio.agents.run",
            description="Run a named agent with a prompt and return its response.",
            parameters=(
                ToolParameter("agent_name", "string", "The registered name of the studio agent that should handle this request. It must match one of the names returned by studio.agents.list, because the studio only runs agents it was configured with. Use it to choose which specialist answers the prompt. An unknown name returns an error instead of running a different agent."),
                ToolParameter("prompt", "string", "The user message the selected agent receives as its task for this run. The agent treats it exactly like a prompt passed to its own run method, with its own tools, middleware, and loop settings. Provide the complete request in plain language, including any context the agent needs, because the studio adds nothing else. The agent's final reply is returned as the tool result."),
            ),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "studio"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        agent_name = str(call.arguments.get("agent_name") or "")
        prompt = str(call.arguments.get("prompt") or "")
        if not agent_name:
            return ToolResult.error("studio.agents.run", "Missing agent_name parameter.")
        if not prompt:
            return ToolResult.error("studio.agents.run", "Missing prompt parameter.")
        agent = self._agents.get(agent_name)
        if agent is None:
            return ToolResult.error("studio.agents.run", f"Agent '{agent_name}' not found.")
        reply = await agent.generate_reply(prompt)
        return ToolResult.success("studio.agents.run", reply.content)


class StudioToolsListTool(BaseTool):
    def __init__(self, tools: Sequence[BaseTool]) -> None:
        self._tools = tuple(tools)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="studio.tools.list",
            description="List available tools and their specifications.",
            parameters=(),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "studio"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        specs = [McpSchema.tool_spec_to_mcp_tool(tool.spec()) for tool in self._tools]
        return ToolResult.success("studio.tools.list", json.dumps(specs, indent=2))


class StudioStrategiesListTool(BaseTool):
    def __init__(self, strategy_names: Sequence[str]) -> None:
        self._names = tuple(strategy_names)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="studio.strategies.list",
            description="List available reasoning and orchestration strategies.",
            parameters=(),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "studio"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        items = [{"name": name, "description": f"Execute the {name} strategy."} for name in self._names]
        return ToolResult.success("studio.strategies.list", json.dumps(items, indent=2))


class StudioStrategiesRunTool(BaseTool):
    def __init__(self, strategy_names: Sequence[str]) -> None:
        self._names = tuple(strategy_names)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="studio.strategies.run",
            description="Run a named strategy with a prompt (placeholder).",
            parameters=(
                ToolParameter("strategy_name", "string", "The name of the registered strategy to describe for this request. It must be one of the names returned by studio.strategies.list, which is the set the studio was configured with. Use it when a client wants to know how a strategy would treat an input. Strategy execution itself requires a runner, so the result reports the strategy and input rather than running a model."),
                ToolParameter("prompt", "string", "Optional input text to associate with the strategy request. It is echoed back in the result so a client can see which input the strategy description refers to. Provide it when the caller wants the response tied to a concrete task. It does not cause any model call, because strategy execution needs a runner that the studio does not provide here.", required=False),
            ),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "studio"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        strategy_name = str(call.arguments.get("strategy_name") or "")
        prompt = str(call.arguments.get("prompt") or "")
        if not strategy_name:
            return ToolResult.error("studio.strategies.run", "Missing strategy_name parameter.")
        if strategy_name not in self._names:
            return ToolResult.error("studio.strategies.run", f"Unknown strategy: {strategy_name}")
        return ToolResult.success(
            "studio.strategies.run",
            json.dumps({"strategy": strategy_name, "input": prompt, "status": "not_executed", "note": "Strategy execution requires a runner. Use studio.agents.run for full execution."}, indent=2),
        )


class StudioPromptsListTool(BaseTool):
    def __init__(self, prompt_families: Mapping[str, Sequence[str]]) -> None:
        self._families = prompt_families

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="studio.prompts.list",
            description="List available prompt templates grouped by family.",
            parameters=(
                ToolParameter("family", "string", "An optional prompt family name used to narrow the listing. When it is provided, only prompt keys from that family are returned, compared without regard to letter case. Leave it out to list every prompt family the studio exposes. Use it to keep responses small when the prompt registry is large.", required=False),
            ),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "studio"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        family_filter = (call.arguments.get("family") or "").strip()
        result: dict[str, list[str]] = {}
        for family, keys in self._families.items():
            if family_filter and family_filter.lower() != family.lower():
                continue
            result[family] = list(keys)
        return ToolResult.success("studio.prompts.list", json.dumps(result, indent=2))


class StudioPromptsGetTool(BaseTool):
    def __init__(self, prompt_content: Mapping[str, str]) -> None:
        self._content = prompt_content

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="studio.prompts.get",
            description="Get the content of a named prompt template.",
            parameters=(
                ToolParameter("name", "string", "The key of the prompt template whose full text should be returned. It must match a key from studio.prompts.list or the MCP prompts/list response, including its family prefix. Use it to retrieve the exact text of a built-in or studio-supplied prompt before reusing it. An unknown key returns a result marked as not found with empty content."),
            ),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "studio"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        name = str(call.arguments.get("name") or "")
        content = self._content.get(name)
        if content is None:
            return ToolResult.success("studio.prompts.get", json.dumps({"name": name, "found": False, "content": ""}, indent=2))
        return ToolResult.success("studio.prompts.get", json.dumps({"name": name, "found": True, "content": content}, indent=2))


class StudioPipelinesListTool(BaseTool):
    def __init__(self, pipeline_names: Sequence[str]) -> None:
        self._names = tuple(pipeline_names)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="studio.pipelines.list",
            description="List available pipeline types for multi-agent orchestration.",
            parameters=(),
            permission=ToolPermission.EXECUTE,
            metadata={"source": "studio"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        items = [{"name": name, "description": f"Execute a {name} pipeline."} for name in self._names]
        return ToolResult.success("studio.pipelines.list", json.dumps(items, indent=2))
