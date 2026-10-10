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
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.settings import AgentFallbackSettings, AgentLoopSettings
from vidbyte.lib.enums import ModelProvider
from vidbyte.tools.base import _ToolWrapper
from vidbyte.tools.catalog import Tools

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager
    from vidbyte.lib.dataclasses.agents import AgentForkSettings, FallbackModel


class AgentForker:
    """Stateless owner of BaseAgent fork logic driven by AgentForkSettings."""

    @classmethod
    def fork(cls, agent: BaseAgent, settings: AgentForkSettings) -> BaseAgent:
        # Builds an isolated child agent branch with resolved config, copied state, and fresh lineage.
        child_run_id = cls._run_id(agent, settings.run_id)
        # The child edits its own copy of the parent's managed context window, so branch edits never reach the parent.
        child_manager = cls._context_manager(agent, settings)
        child = BaseAgent(
            name=settings.name or agent.name,
            runtime=settings.runtime if settings.runtime is not None else (agent.runtime_config_obj or agent.runtime_type),
            tools=cls._tool_items(agent, settings, child_manager),
            permission_policy=agent.permission_policy,
            agent_loop_settings=cls._loop_settings(agent, settings),
            middleware=agent.middleware if settings.middleware is None else settings.middleware,
            system_prompt=agent.system_prompt if settings.system_prompt is None else settings.system_prompt,
            # The parent's key belongs to its own vendor, so a child on another provider resolves its own credential.
            api_key=cls._api_key(agent, settings),
            provider=agent.runner_config.provider if settings.provider is None else settings.provider,
            model_name=agent.runner_config.model_name if settings.model_name is None else settings.model_name,
            temperature=agent.runner_config.temperature if settings.temperature is None else settings.temperature,
            timeout_seconds=agent.runner_config.timeout_seconds,
            run_id=child_run_id,
            description=agent.description,
            capabilities=agent.capabilities,
            agent_metadata=agent.agent_metadata,
            context_items=agent.context_items if settings.context_items is None else settings.context_items,
            context_manager=child_manager,
            algorithm=agent.algorithm if settings.algorithm is None else settings.algorithm,
            metadata=cls._metadata(agent, child_run_id, settings.metadata),
            tracer=agent._tracer,
            output_schema=agent.output_schema if settings.output_schema is None else settings.output_schema,
            handoff=agent._handoff_spec if settings.handoff is None else settings.handoff,
            trace_option=settings.trace_option if settings.trace_option is not None else agent._trace_option,
            # Backups the parent named by bare model name keep the parent's provider, even when the child switches.
            fallback=cls._fallback(agent, settings),
        )
        if settings.mcp if settings.inherit_mcp is None else settings.inherit_mcp:
            child._pending_mcp_configs.extend(agent._mcp_configs_for_fork())
        cls._copy_run_state(agent, child, settings)
        return child

    @staticmethod
    def _context_manager(agent: BaseAgent, settings: AgentForkSettings) -> ContextManager | None:
        # @intent fork-isolates-context-manager
        # An explicit override is used as-is; an inherited manager is copied so the child cannot rewrite the parent's.
        if settings.context_manager is not None:
            return settings.context_manager
        return agent.context_manager.copy() if agent.context_manager is not None else None

    @staticmethod
    def _api_key(agent: BaseAgent, settings: AgentForkSettings) -> str | None:
        # @intent fork-key-never-crosses-providers
        # Sending the parent vendor's secret to another vendor leaks it and fails auth; None lets the
        # child's provider read its own env key. Same-provider forks (or model-only overrides) keep the key.
        if settings.provider is None:
            return agent.runner_config.api_key
        child_provider = settings.provider.value if isinstance(settings.provider, ModelProvider) else str(settings.provider)
        if child_provider.strip().lower() != str(agent.runner_config.provider or "").strip().lower():
            return None
        return agent.runner_config.api_key

    @staticmethod
    def _fallback(agent: BaseAgent, settings: AgentForkSettings) -> Sequence[str | FallbackModel] | AgentFallbackSettings | None:
        # @intent fork-keeps-resolved-fallback-providers
        # A bare backup name means "this model on the parent's provider". Re-resolving the parent's raw spec
        # against a child on another provider would move it to a model that vendor does not serve, so a
        # provider-switching child inherits the parent's resolved backups, each carrying only its own vendor's key.
        if settings.fallback is not None:
            return settings.fallback
        child_provider = settings.provider.value if isinstance(settings.provider, ModelProvider) else str(settings.provider or "")
        if settings.provider is None or child_provider.strip().lower() == str(agent.runner_config.provider or "").strip().lower():
            return agent._fallback_spec
        if agent.fallback is None:
            return None
        return AgentFallbackSettings(models=agent.fallback.models[1:], fallback_on=agent.fallback.fallback_on)

    @staticmethod
    def _loop_settings(agent: BaseAgent, settings: AgentForkSettings) -> AgentLoopSettings:
        # Resolves inherited or overridden loop settings; max_iterations replaces only that field, all others inherit.
        if settings.agent_loop_settings is not None:
            return settings.agent_loop_settings
        if settings.max_iterations is None:
            return agent.agent_loop_settings
        base = agent.agent_loop_settings
        return AgentLoopSettings(
            max_iterations=settings.max_iterations,
            max_tokens=base.max_tokens,
            max_tool_calls=base.max_tool_calls,
            max_queued_prompts=base.max_queued_prompts,
            max_parallel_tool_calls=base.max_parallel_tool_calls,
            max_retries=base.max_retries,
            timeout_seconds=base.timeout_seconds,
            context_window_budget=base.context_window_budget,
            compaction_trigger_tokens=base.compaction_trigger_tokens,
            compaction_target_tokens=base.compaction_target_tokens,
            allowed_tools=base.allowed_tools,
            tool_error_policy=base.tool_error_policy,
            tool_settings=base.tool_settings,
            output_contracts=base.output_contracts,
            max_contract_rejections=base.max_contract_rejections,
        )

    @classmethod
    def _tool_items(cls, agent: BaseAgent, settings: AgentForkSettings, child_manager: ContextManager | None) -> tuple[object, ...]:
        # Returns child-safe tools by removing parent MCP bridged tools, cloning bound builtins, and applying deltas.
        tools = settings.tools
        selected = tools.all() if isinstance(tools, Tools) else (agent._agent_tool_items if tools is None else tuple(tools))
        parent_mcp_tools = set(agent._mcp_bridged_tools_for_fork())
        child_items = [cls._clone_tool(tool, agent.context_manager, child_manager) for tool in selected if tool not in parent_mcp_tools]
        child_items.extend(cls._clone_tool(tool, agent.context_manager, child_manager) for tool in settings.add_tools)
        if not settings.drop_tools:
            return tuple(child_items)
        dropped = {str(name) for name in settings.drop_tools}
        return tuple(tool for tool in child_items if agent._tool_name(tool) not in dropped)

    @classmethod
    def _clone_tool(cls, tool: object, parent_manager: ContextManager | None, child_manager: ContextManager | None) -> object:
        # Clones SDK tools that carry mutable agent bindings, preserving custom tools by identity.
        if isinstance(tool, _ToolWrapper):
            # A customize() or with_activity() view clones the tool it wraps and keeps the same view over the copy.
            inner = cls._clone_tool(tool.wrapped_tool, parent_manager, child_manager)
            return tool if inner is tool.wrapped_tool else tool._rewrap(inner)
        clone = getattr(tool, "clone_for_fork", None)
        if callable(clone):
            return clone()
        # @intent fork-rebinds-context-tools
        # Tools writing to the parent's context manager are rebound to the child's, matching what the child renders.
        rebind = getattr(tool, "rebind_context_manager", None)
        return rebind(parent_manager, child_manager) if callable(rebind) else tool

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
