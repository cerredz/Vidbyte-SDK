"""Context Protocol Header

Description:
    Houses AgentForker, the utility class that owns all BaseAgent fork logic.
Purpose:
    Keeps base.py focused on agent execution by extracting fork config
    resolution, tool cloning, lineage metadata, and run-state carry into one
    cohesive place driven entirely by a validated AgentForkSettings.
Architecture:
    - AgentForker: Stateless utility whose functions take a live parent agent
      and an AgentForkSettings, and return an isolated child BaseAgent branch.
Relations:
    Invoked by BaseAgent.fork. Reads inheritable state off the parent agent and
    constructs the child via BaseAgent. Settings/validation live in
    vidbyte.lib.dataclasses.agents; fork errors live in vidbyte.lib.errors.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Mapping

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.tools.catalog import Tools

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.agents import AgentForkSettings


class AgentForker:
    """Stateless owner of BaseAgent fork logic driven by AgentForkSettings."""

    @classmethod
    def fork(cls, agent: BaseAgent, settings: AgentForkSettings) -> BaseAgent:
        # Builds an isolated child agent branch with resolved config, copied state, and fresh lineage.
        child_run_id = cls._run_id(agent, settings.run_id)
        child = BaseAgent(
            name=settings.name or agent.name,
            runtime=settings.runtime if settings.runtime is not None else (agent.runtime_config_obj or agent.runtime_type),
            tools=cls._tool_items(agent, settings),
            permission_policy=agent.permission_policy,
            agent_loop_settings=cls._loop_settings(agent, settings),
            middleware=agent.middleware if settings.middleware is None else settings.middleware,
            system_prompt=agent.system_prompt if settings.system_prompt is None else settings.system_prompt,
            api_key=agent.runner_config.api_key,
            provider=agent.runner_config.provider if settings.provider is None else settings.provider,
            model_name=agent.runner_config.model_name if settings.model_name is None else settings.model_name,
            temperature=agent.runner_config.temperature if settings.temperature is None else settings.temperature,
            run_id=child_run_id,
            description=agent.description,
            capabilities=agent.capabilities,
            agent_metadata=agent.agent_metadata,
            context_items=agent.context_items if settings.context_items is None else settings.context_items,
            context_manager=agent.context_manager if settings.context_manager is None else settings.context_manager,
            algorithm=agent.algorithm if settings.algorithm is None else settings.algorithm,
            metadata=cls._metadata(agent, child_run_id, settings.metadata),
            tracer=agent._tracer,
            output_schema=agent.output_schema if settings.output_schema is None else settings.output_schema,
            handoff=agent._handoff_spec if settings.handoff is None else settings.handoff,
            trace_option=settings.trace_option if settings.trace_option is not None else agent._trace_option,
            fallback=agent._fallback_spec if settings.fallback is None else settings.fallback,
        )
        if settings.mcp if settings.inherit_mcp is None else settings.inherit_mcp:
            child._pending_mcp_configs.extend(agent._mcp_configs_for_fork())
        cls._copy_run_state(agent, child, settings)
        return child

    @staticmethod
    def _loop_settings(agent: BaseAgent, settings: AgentForkSettings) -> AgentLoopSettings:
        # Resolves inherited or overridden loop settings, with max_iterations as a shallow delta.
        if settings.agent_loop_settings is not None:
            return settings.agent_loop_settings
        if settings.max_iterations is None:
            return agent.agent_loop_settings
        base = agent.agent_loop_settings
        return AgentLoopSettings(
            max_iterations=settings.max_iterations,
            max_tokens=base.max_tokens,
            max_tool_calls=base.max_tool_calls,
            max_parallel_tool_calls=base.max_parallel_tool_calls,
            max_retries=base.max_retries,
            timeout_seconds=base.timeout_seconds,
            context_window_budget=base.context_window_budget,
            compaction_trigger_tokens=base.compaction_trigger_tokens,
            compaction_target_tokens=base.compaction_target_tokens,
            allowed_tools=base.allowed_tools,
        )

    @classmethod
    def _tool_items(cls, agent: BaseAgent, settings: AgentForkSettings) -> tuple[object, ...]:
        # Returns child-safe tools by removing parent MCP bridged tools, cloning bound builtins, and applying deltas.
        tools = settings.tools
        selected = tools.all() if isinstance(tools, Tools) else (agent._agent_tool_items if tools is None else tuple(tools))
        parent_mcp_tools = set(agent._mcp_bridged_tools_for_fork())
        child_items = [cls._clone_tool(tool) for tool in selected if tool not in parent_mcp_tools]
        child_items.extend(cls._clone_tool(tool) for tool in settings.add_tools)
        if not settings.drop_tools:
            return tuple(child_items)
        dropped = {str(name) for name in settings.drop_tools}
        return tuple(tool for tool in child_items if agent._tool_name(tool) not in dropped)

    @staticmethod
    def _clone_tool(tool: object) -> object:
        # Clones SDK tools that carry mutable agent bindings, preserving custom tools by identity.
        clone = getattr(tool, "clone_for_fork", None)
        if callable(clone):
            return clone()
        return tool

    @staticmethod
    def _run_id(agent: BaseAgent, explicit_run_id: str | None) -> str:
        # Returns an explicit child run id or creates a lineage-friendly fork id.
        if explicit_run_id is not None:
            return explicit_run_id
        suffix = uuid.uuid4().hex[:8]
        parent_run_id = agent.runner_config.run_id
        return f"{parent_run_id}:fork:{suffix}" if parent_run_id else f"fork:{suffix}"

    @staticmethod
    def _metadata(agent: BaseAgent, child_run_id: str, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
        # Merges parent metadata, caller overrides, and definitive fork lineage metadata.
        fork_depth = int(agent.metadata.get("fork_depth", 0) or 0) + 1
        parent_identity = agent.runner_config.run_id or agent.name
        lineage = {
            "forked_from": parent_identity,
            "fork_depth": fork_depth,
            "fork_parent_agent_name": agent.name,
            "fork_parent_run_id": agent.runner_config.run_id,
            "fork_child_run_id": child_run_id,
        }
        return {**agent.metadata, **dict(overrides or {}), **lineage}

    @staticmethod
    def _copy_run_state(agent: BaseAgent, child: BaseAgent, settings: AgentForkSettings) -> None:
        # Copies optional transcript and lifecycle state while leaving last-run artifacts reset.
        if settings.history is not None:
            child.history = list(settings.history)
        elif settings.include_history:
            child.history = list(agent.history)
        if settings.include_run_state:
            child.handoffs = list(agent.handoffs)
            child.last_handoff = child.handoffs[-1] if child.handoffs else None
            child._tool_call_contexts = list(agent._tool_call_contexts)


__all__ = ["AgentForker"]
