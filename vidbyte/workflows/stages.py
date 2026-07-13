"""FILE: vidbyte/workflows/stages.py
PURPOSE: Adapts Python callbacks and Vidbyte agents to the workflow Stage protocol.
ROLE IN CODEBASE: Built by SDK users, stored by graph.py, and invoked under policy by machine.py.

ARCHITECTURE NOTE:
    A stage performs work and proposes StageResult; it never commits state or
    selects a target. AgentStage forks without history by default so repeated
    visits and concurrent machine runs do not accidentally share conversation
    state. A context-aware factory can bind run-ledger tracking tools per visit.

PUBLIC API INVENTORY:
    CallableStage: Invokes one sync/async StageContext callback.
    AgentStage: Builds agent input and maps AgentMessage to StageResult.

COMMON MODIFICATION PATTERNS:
    Add another execution adapter only when an SDK actor cannot be represented
    as a callback or BaseAgent. Keep retries, timeouts, validation, and routing
    in machine.py so adapters have no hidden control flow.

WHAT NOT TO DO IN THIS FILE:
    1. Do not commit or mutate the machine's authoritative state reference.
    2. Do not map outcomes to stage names; graph.py owns that declaration.
    3. Do not add retries around agent calls; StagePolicy owns retries.
    4. Do not automatically inject full workflow history into prompts.

KNOWN EDGE CASES:
    fresh_fork=False intentionally permits shared agent history and makes
    concurrent safety the caller's responsibility. Factories that return the
    same agent instance carry the same risk.

COMMON ERRORS:
    WorkflowDefinitionError for incompatible fork settings or bad factories.
    Agent/provider failures propagate to machine.py for StagePolicy handling.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Existing agent tests plus inline workflow smoke cover adapter integration.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Generic

from vidbyte.agents import AgentForkSettings, AgentInput, AgentLoopSettings, AgentMessage, BaseAgent
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.middleware.builtins import ModelRetryMiddleware
from vidbyte.workflows.budget import UsageReport
from vidbyte.workflows.capabilities import ActionPolicyMiddleware, AgentModelRoute, StageCapabilities, ToolCapabilityResolver
from vidbyte.workflows.contracts import StageContext, StageResult, StateT, WorkflowCommand
from vidbyte.workflows.detection import StuckDetectorMiddleware
from vidbyte.workflows.detours import SignalMatcher, WorkflowSignal, _ToolDetourMiddleware
from vidbyte.workflows.errors import WorkflowDefinitionError, WorkflowStuckError


class CallableStage(Generic[StateT]):
    """Adapts one synchronous or asynchronous stage callback."""

    def __init__(self, callback: Callable[[StageContext[StateT]], StageResult[StateT] | WorkflowCommand[StateT] | Awaitable[StageResult[StateT] | WorkflowCommand[StateT]]], *, name: str | None = None) -> None:
        # Stores the callback and a stable diagnostic name.
        if not callable(callback):
            raise WorkflowDefinitionError("CallableStage callback must be callable.", details={"actual_type": type(callback).__name__})
        self._callback = callback
        self._name = _resolved_name(name, callback, "callable_stage")

    @property
    def name(self) -> str:
        # Returns the adapter's diagnostic name; graph stage names remain authoritative.
        return self._name

    async def run(self, context: StageContext[StateT]) -> StageResult[StateT] | WorkflowCommand[StateT]:
        # Invokes the callback and awaits it only when necessary.
        value = self._callback(context)
        return await value if inspect.isawaitable(value) else value


class AgentStage(Generic[StateT]):
    """Adapts a fixed or context-created BaseAgent to a typed workflow stage."""

    supports_execution_policy = True

    def __init__(self, agent: BaseAgent | Callable[[StageContext[StateT]], BaseAgent], prompt_builder: Callable[[StageContext[StateT]], str | AgentInput], result_builder: Callable[[AgentMessage, StageContext[StateT]], StageResult[StateT] | WorkflowCommand[StateT] | Awaitable[StageResult[StateT] | WorkflowCommand[StateT]]], *, fresh_fork: bool = True, fork_settings: AgentForkSettings | None = None, name: str | None = None) -> None:
        # Validates isolation settings and stores the agent input/output adapters.
        if not isinstance(agent, BaseAgent) and not callable(agent):
            raise WorkflowDefinitionError("AgentStage agent must be BaseAgent or a callable factory.", details={"actual_type": type(agent).__name__})
        if not callable(prompt_builder) or not callable(result_builder):
            raise WorkflowDefinitionError("AgentStage prompt_builder and result_builder must be callable.", details={"prompt_builder_type": type(prompt_builder).__name__, "result_builder_type": type(result_builder).__name__})
        if not isinstance(fresh_fork, bool):
            raise WorkflowDefinitionError("AgentStage fresh_fork must be a boolean.", details={"actual_type": type(fresh_fork).__name__})
        if fork_settings is not None and not isinstance(fork_settings, AgentForkSettings):
            raise WorkflowDefinitionError("AgentStage fork_settings must be AgentForkSettings when provided.", details={"actual_type": type(fork_settings).__name__})
        if fresh_fork and fork_settings is not None and (fork_settings.include_history or fork_settings.history is not None):
            raise WorkflowDefinitionError("AgentStage fresh forks cannot include parent or explicit history.", details={"adapter": name or "agent_stage", "include_history": fork_settings.include_history, "explicit_history": fork_settings.history is not None})
        self._agent_source = agent
        self._prompt_builder = prompt_builder
        self._result_builder = result_builder
        self._fresh_fork = fresh_fork
        self._fork_settings = fork_settings or AgentForkSettings(include_history=False)
        self._name = _resolved_name(name, agent, "agent_stage")

    @property
    def name(self) -> str:
        # Returns the adapter's diagnostic name; graph stage names remain authoritative.
        return self._name

    async def run(self, context: StageContext[StateT]) -> StageResult[StateT] | WorkflowCommand[StateT]:
        # Applies the default policy shell so all AgentStage invocations get stuck detection.
        return await self.run_with_policy(context, capabilities=StageCapabilities(), model_route=None)

    async def run_with_policy(self, context: StageContext[StateT], *, capabilities: StageCapabilities | None, model_route: AgentModelRoute | None, detour_rules: tuple[tuple[str, SignalMatcher], ...] = (), model_call_limit: int | None = None) -> StageResult[StateT] | WorkflowCommand[StateT]:
        # Forks an exact model/tool/middleware profile and maps its evidence to a command.
        agent, action_middleware = await self._resolve_policy_agent(context, capabilities or StageCapabilities(), model_route, detour_rules, model_call_limit)
        prompt = self._prompt_builder(context)
        reply = await agent.arun(prompt)
        self._raise_if_stuck(reply, context)
        detour_command = self._tool_detour_command(reply, action_middleware)
        if detour_command is not None:
            return replace(detour_command, usage=_usage_from_reply(reply))
        result = self._result_builder(reply, context)
        resolved = await result if inspect.isawaitable(result) else result
        usage = _usage_from_reply(reply)
        signals = tuple(action_middleware.signals) if action_middleware is not None else ()
        evidence = {
            "agent_provider": reply.metadata.get("provider"),
            "agent_model": reply.metadata.get("model_name"),
            "action_decisions": tuple({"allowed": item.allowed, "code": item.code, "reason": item.reason, "metadata": dict(item.metadata)} for item in (action_middleware.decisions if action_middleware is not None else ())),
        }
        if isinstance(resolved, StageResult):
            return WorkflowCommand(update={"__root__": resolved.state}, outcome=resolved.outcome, signals=signals, usage=usage, metadata={**dict(resolved.metadata), **evidence})
        if not isinstance(resolved, WorkflowCommand):
            raise TypeError(f"AgentStage result_builder must return StageResult or WorkflowCommand, got {type(resolved).__name__}.")
        combined_usage = resolved.usage.combined_with(usage) if resolved.usage is not None else usage
        return replace(resolved, signals=(*resolved.signals, *signals), usage=combined_usage, metadata={**dict(resolved.metadata), **evidence})

    def _resolve_agent(self, context: StageContext[StateT]) -> BaseAgent:
        # Resolves the fixed agent or per-visit factory and applies default isolation.
        agent = self._agent_source if isinstance(self._agent_source, BaseAgent) else self._agent_source(context)
        if not isinstance(agent, BaseAgent):
            raise TypeError(f"AgentStage agent factory must return BaseAgent, got {type(agent).__name__}.")
        return agent.fork(self._fork_settings) if self._fresh_fork else agent

    async def _resolve_policy_agent(self, context: StageContext[StateT], capabilities: StageCapabilities, model_route: AgentModelRoute | None, detour_rules: tuple[tuple[str, SignalMatcher], ...], model_call_limit: int | None) -> tuple[BaseAgent, ActionPolicyMiddleware | None]:
        # Resolves MCP tools first, then removes denied schemas before constructing a fork.
        base = self._agent_source if isinstance(self._agent_source, BaseAgent) else self._agent_source(context)
        if not isinstance(base, BaseAgent):
            raise TypeError(f"AgentStage agent factory must return BaseAgent, got {type(base).__name__}.")
        await base._ensure_mcp_connected()
        configured_tools = self._fork_settings.tools
        selected_tools = tuple(configured_tools.all()) if hasattr(configured_tools, "all") else (tuple(base._agent_tool_items) if configured_tools is None else tuple(configured_tools))
        selected_tools = (*selected_tools, *tuple(self._fork_settings.add_tools))
        if self._fork_settings.drop_tools:
            dropped = set(self._fork_settings.drop_tools)
            selected_tools = tuple(tool for tool in selected_tools if base._tool_name(tool) not in dropped)
        visible_tools = ToolCapabilityResolver.resolve(selected_tools, capabilities.tools)
        existing_middleware = base.middleware if self._fork_settings.middleware is None else tuple(self._fork_settings.middleware)
        action_middleware = ActionPolicyMiddleware(context.stage, capabilities.action_policy) if capabilities.action_policy.guards else None
        detour_middleware = _ToolDetourMiddleware(detour_rules) if detour_rules else None
        policy_middleware = tuple(item for item in (action_middleware, StuckDetectorMiddleware(), detour_middleware) if item is not None)
        route_middleware = tuple(factory() for factory in (model_route.middleware_factories if model_route else ()))
        retry_middleware: tuple[AgentMiddleware, ...] = ()
        if model_route is not None and model_route.model_retry is not None:
            retry_middleware = (ModelRetryMiddleware(max_attempts=model_route.model_retry.max_attempts, sleep_seconds=model_route.model_retry.sleep_seconds),)
        loop_settings = self._fork_settings.agent_loop_settings
        max_iterations = self._fork_settings.max_iterations
        if model_route is not None and model_route.loop_settings is not None:
            loop_settings = model_route.loop_settings
            max_iterations = None
        elif model_route is not None and model_route.max_iterations is not None:
            loop_settings = None
            max_iterations = model_route.max_iterations
        if model_call_limit is not None:
            if model_call_limit <= 0:
                raise ValueError("AgentStage model_call_limit must be positive when provided.")
            if loop_settings is not None:
                loop_settings = _bounded_loop_settings(loop_settings, model_call_limit)
                max_iterations = None
            else:
                max_iterations = min(max_iterations, model_call_limit) if max_iterations is not None else model_call_limit
        settings = replace(
            self._fork_settings,
            tools=visible_tools,
            add_tools=(),
            drop_tools=(),
            middleware=(*policy_middleware, *route_middleware, *retry_middleware, *existing_middleware),
            include_history=False,
            history=None,
            run_id=f"{context.idempotency_key}:agent",
            provider=model_route.provider if model_route and model_route.provider is not None else self._fork_settings.provider,
            model_name=model_route.model_name if model_route and model_route.model_name is not None else self._fork_settings.model_name,
            temperature=model_route.temperature if model_route and model_route.temperature is not None else self._fork_settings.temperature,
            runner_options=model_route.runner_options if model_route is not None else self._fork_settings.runner_options,
            agent_loop_settings=loop_settings,
            max_iterations=max_iterations,
        )
        child = base.fork(settings)
        child.metadata.update({"workflow_run_id": context.run_id, "workflow_stage": context.stage, "workflow_visit": context.visit, "workflow_idempotency_key": context.idempotency_key})
        return child, action_middleware

    @staticmethod
    def _raise_if_stuck(reply: AgentMessage, context: StageContext[StateT]) -> None:
        # Converts the controlled middleware abort into a workflow lifecycle failure.
        reason = reply.metadata.get("middleware_abort_reason")
        decision = reply.metadata.get("middleware_decision", {})
        if reason != "stuck_detected" and (not isinstance(decision, dict) or decision.get("reason") != "stuck_detected"):
            return
        evidence = decision.get("metadata", {}) if isinstance(decision, dict) else {}
        raise WorkflowStuckError("Agent stage matched a configured stuck signature.", details={"run_id": context.run_id, "stage": context.stage, **dict(evidence or {})})

    @staticmethod
    def _tool_detour_command(reply: AgentMessage, action_middleware: ActionPolicyMiddleware | None) -> WorkflowCommand[StateT] | None:
        # Converts a safe post-tool abort to a machine-owned detour signal command.
        if reply.metadata.get("middleware_abort_reason") != "workflow_detour_requested":
            return None
        decision = reply.metadata.get("middleware_decision", {})
        evidence = decision.get("metadata", {}) if isinstance(decision, dict) else {}
        signals = tuple(WorkflowSignal(str(item["signal_type"]), str(item["source"]), item.get("data", {})) for item in evidence.get("signals", ()) if isinstance(item, dict))
        if action_middleware is not None:
            signals = (*action_middleware.signals, *signals)
        return WorkflowCommand(outcome="success", signals=signals, metadata={"tool_boundary_detour": True, "candidate_rule_ids": tuple(evidence.get("candidate_rule_ids", ()))})


def _resolved_name(name: str | None, source: object, fallback: str) -> str:
    # Derives one non-empty diagnostic name from explicit or source metadata.
    candidate = name or getattr(source, "name", None) or getattr(source, "__name__", None) or fallback
    resolved = str(candidate).strip()
    if not resolved:
        raise WorkflowDefinitionError("Stage adapter name cannot be empty.", details={"fallback": fallback})
    return resolved


def _bounded_loop_settings(value: AgentLoopSettings, model_call_limit: int) -> AgentLoopSettings:
    # Clones all loop policy while intersecting model iterations with root remainder.
    max_iterations = min(value.max_iterations, model_call_limit) if value.max_iterations is not None else model_call_limit
    return AgentLoopSettings(
        max_iterations=max_iterations,
        max_tokens=value.max_tokens,
        max_tool_calls=value.max_tool_calls,
        max_queued_prompts=value.max_queued_prompts,
        max_parallel_tool_calls=value.max_parallel_tool_calls,
        max_retries=value.max_retries,
        timeout_seconds=value.timeout_seconds,
        context_window_budget=value.context_window_budget,
        compaction_trigger_tokens=value.compaction_trigger_tokens,
        compaction_target_tokens=value.compaction_target_tokens,
        allowed_tools=value.allowed_tools,
        tool_error_policy=value.tool_error_policy,
        tool_settings=value.tool_settings,
        output_contracts=value._output_contracts,
        max_contract_rejections=value.max_contract_rejections,
    )


def _usage_from_reply(reply: AgentMessage) -> UsageReport:
    # Maps provider-independent agent counters to honest additive workflow usage.
    metadata = reply.metadata
    iterations = metadata.get("iteration_count", 0)
    tools = metadata.get("tool_call_count", 0)
    tokens = metadata.get("tokens_used")
    cost = metadata.get("cost_usd")
    return UsageReport(
        model_calls=int(iterations) if isinstance(iterations, int) and not isinstance(iterations, bool) and iterations >= 0 else 0,
        tool_calls=int(tools) if isinstance(tools, int) and not isinstance(tools, bool) and tools >= 0 else 0,
        input_tokens=metadata.get("input_tokens") if isinstance(metadata.get("input_tokens"), int) else None,
        output_tokens=metadata.get("output_tokens") if isinstance(metadata.get("output_tokens"), int) else None,
        total_tokens=tokens if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0 else None,
        cost_usd=float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0 else None,
        provider=metadata.get("provider") if isinstance(metadata.get("provider"), str) else None,
        model=metadata.get("model_name") if isinstance(metadata.get("model_name"), str) else None,
    )


__all__ = ["AgentStage", "CallableStage"]
