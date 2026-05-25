"""Context Protocol Header

Description:
    Defines the internal direct execution runtime for Vidbyte agents.
Purpose:
    Keeps agent loop execution, context-window construction, tool execution,
    permission checks, and provider-reported token accounting out of BaseAgent.
Architecture:
    - AgentRuntime: Builds BaseAgentContext and runs direct model/tool loops.
Relations:
    Used by vidbyte.agents.base. Depends on shared context, tool, security, and
    strategy dataclasses without owning modality routing or runner construction.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vidbyte.agents.types import AgentMessage
from vidbyte.context.algorithms import ContextWindowAlgorithm
from vidbyte.context.algorithms.plan_then_implement import (
    build_plan_prompt,
    fallback_plan,
    plan_artifact_from_text,
)
from vidbyte.context.algorithms.reasoning_trace import render_reasoning_trace
from vidbyte.context.algorithms.types import (
    ContextWindowIterationEvent,
    ReasoningTraceConfig,
)
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.context.window import ContextWindow
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig, AgentStopReason
from vidbyte.lib.dataclasses.middleware import MiddlewareAction, MiddlewareContext, MiddlewareDecision, MiddlewareHook
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import PermissionDeniedError, ToolExecutionError, ToolRegistryError
from vidbyte.lib.token_usage import token_usage_from_response
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.middleware import AgentMiddleware, MiddlewarePipeline
from vidbyte.prompts.agentic_loop import append_agentic_loop_prompt
from vidbyte.strategies.types import BaseAgentContext, StrategyContext, StrategyResult
from vidbyte.tools._internal import IS_DONE_TOOL_NAME, with_internal_agent_tools
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionDecision, PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolCallContext, ToolCallState, ToolResult


class AgentRuntime:
    """Internal runtime for direct agent execution."""

    def __init__(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        tools: Tools,
        permission_policy: PermissionPolicy,
        config: AgentRuntimeConfig | None = None,
        middleware: Sequence[AgentMiddleware] = (),
        run_id: str | None = None,
        algorithm: ContextWindowAlgorithm | str | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.user_tools = tools
        self.tools = with_internal_agent_tools(tools)
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()
        self.middleware = MiddlewarePipeline(middleware)
        self.run_id = run_id
        self.algorithm = ContextWindow.resolve_algorithm(algorithm)

    def build_context(
        self,
        message: str,
        *,
        base_context: StrategyContext | None,
        history: Sequence[AgentMessage],
        agent_history: Sequence[AgentMessage],
        agent_metadata: Mapping[str, Any],
        existing_tool_calls: Sequence[ToolCallContext],
        input_metadata: Mapping[str, Any] | None = None,
        modality: ModelModality | None = None,
        agentic_loop: bool = True,
        context_items: Sequence[ContextItem] = (),
        context_manager: ContextManager | None = None,
    ) -> BaseAgentContext:
        """Build the minimal context window passed into direct runners and strategies."""
        del message
        system_prompt = base_context.system_prompt if base_context and base_context.system_prompt else self.system_prompt
        manager = ContextManager()
        if context_manager is not None:
            manager.extend(context_manager.items())
        manager.extend(context_items)
        managed_context = manager.to_context(base_context)
        metadata = {
            **(dict(base_context.metadata) if base_context else {}),
            **dict(agent_metadata),
            **dict(input_metadata or {}),
        }
        if modality is not None:
            metadata["modality"] = modality.value
        return BaseAgentContext(
            system_prompt=append_agentic_loop_prompt(system_prompt) if agentic_loop else system_prompt,
            history=tuple(history) + tuple(agent_history),
            tools=(self.tools if agentic_loop else self.user_tools).specs(),
            file_paths=tuple(managed_context.file_paths),
            strategy_metadata=dict(managed_context.strategy_metadata),
            tool_calls=(*tuple(managed_context.tool_calls), *tuple(existing_tool_calls)),
            responses=tuple(managed_context.responses),
            budget=managed_context.budget,
            artifacts=tuple(managed_context.artifacts),
            memory=managed_context.memory,
            permissions=managed_context.permissions,
            metadata=metadata,
            context_items=tuple(managed_context.context_items),
        )

    async def arun(
        self,
        message: str,
        *,
        runner: object,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> StrategyResult:
        """Run the direct model/tool loop until isDone or a budget stop."""
        run_options = dict(options or {})
        runtime_metadata = dict(metadata or {})
        tool_schemas = self._resolve_tool_schemas(provider)
        messages = self._extract_initial_messages(run_options)
        call_contexts: list[ToolCallContext] = []
        iteration_count = 0
        model_call_count = 0
        tokens_used: int | None = None
        started_at = self.middleware.clock()
        last_response: object | None = None
        trace_count = 0
        runtime_metadata["context_window_reasoning_trace_count"] = trace_count

        decision = await self.middleware.before_run(
            self._middleware_context(
                MiddlewareHook.BEFORE_RUN,
                message=message,
                context=context,
                provider=provider,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                tool_call_count=len(call_contexts),
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=runtime_metadata,
            )
        )
        if decision.action is not MiddlewareAction.CONTINUE:
            result = self._middleware_abort_result(
                decision,
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                contexts=call_contexts,
            )
            return await self._finish_result(
                result,
                message=message,
                context=context,
                provider=provider,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=runtime_metadata,
            )

        context, plan_metadata = await self._prepare_algorithm_context(
            message=message,
            context=context,
            runner=runner,
            provider=provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
            model_call_count=model_call_count,
            call_contexts=call_contexts,
            iteration_count=iteration_count,
            tokens_used=tokens_used,
            started_at=started_at,
            metadata=runtime_metadata,
        )
        if isinstance(context, StrategyResult):
            return await self._finish_result(
                context,
                message=message,
                context=context,
                provider=provider,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=runtime_metadata,
            )
        if plan_metadata:
            runtime_metadata.update(plan_metadata)

        while True:
            stop_result = self._budget_stop(
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                contexts=call_contexts,
            )
            if stop_result is not None:
                return await self._finish_result(
                    stop_result,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=runtime_metadata,
                    model_response=last_response,
                )

            decision = await self.middleware.before_iteration(
                self._middleware_context(
                    MiddlewareHook.BEFORE_ITERATION,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tool_call_count=len(call_contexts),
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=runtime_metadata,
                    model_response=last_response,
                )
            )
            if decision.action is not MiddlewareAction.CONTINUE:
                result = self._middleware_abort_result(
                    decision,
                    iteration_count=iteration_count,
                    tokens_used=tokens_used,
                    contexts=call_contexts,
                )
                return await self._finish_result(
                    result,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=runtime_metadata,
                    model_response=last_response,
                )

            call_options = self._build_iteration_call_options(run_options, context, tool_schemas, messages)
            raw_result, model_call_count = await self._invoke_with_middleware(
                runner,
                message,
                call_options,
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                call_contexts=call_contexts,
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=runtime_metadata,
            )
            if isinstance(raw_result, StrategyResult):
                return await self._finish_result(
                    raw_result,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=runtime_metadata,
                    model_response=last_response,
                )
            last_response = raw_result
            iteration_count += 1
            runner_metadata = dict(runner_output_metadata(raw_result))
            tokens_used = self._add_token_usage(tokens_used, token_usage_from_response(raw_result, runner_metadata))

            decision = await self.middleware.after_model_response(
                self._middleware_context(
                    MiddlewareHook.AFTER_MODEL_RESPONSE,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tool_call_count=len(call_contexts),
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=runtime_metadata,
                    model_response=raw_result,
                )
            )
            if decision.action is not MiddlewareAction.CONTINUE:
                result = self._middleware_abort_result(
                    decision,
                    iteration_count=iteration_count,
                    tokens_used=tokens_used,
                    contexts=call_contexts,
                )
                return await self._finish_result(
                    result,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=runtime_metadata,
                    model_response=raw_result,
                )

            tool_calls = ToolsFormatter.parse_tool_calls(raw_result, provider)
            if not tool_calls:
                assistant_output = runner_output_text(raw_result)
                messages.append(self._assistant_message(assistant_output))
                decision = await self.middleware.after_iteration(
                    self._middleware_context(
                        MiddlewareHook.AFTER_ITERATION,
                        message=message,
                        context=context,
                        provider=provider,
                        iteration_count=iteration_count,
                        model_call_count=model_call_count,
                        tool_call_count=len(call_contexts),
                        tokens_used=tokens_used,
                        started_at=started_at,
                        metadata=runtime_metadata,
                        model_response=raw_result,
                    )
                )
                if decision.action is not MiddlewareAction.CONTINUE:
                    result = self._middleware_abort_result(
                        decision,
                        iteration_count=iteration_count,
                        tokens_used=tokens_used,
                        contexts=call_contexts,
                    )
                    return await self._finish_result(
                        result,
                        message=message,
                        context=context,
                        provider=provider,
                        iteration_count=iteration_count,
                        model_call_count=model_call_count,
                        tokens_used=tokens_used,
                        started_at=started_at,
                        metadata=runtime_metadata,
                        model_response=raw_result,
                    )
                trace_count += self._append_reasoning_trace_if_needed(
                    messages,
                    request=message,
                    iteration_count=iteration_count,
                    assistant_output=assistant_output,
                    current_iteration_contexts=(),
                )
                runtime_metadata["context_window_reasoning_trace_count"] = trace_count
                continue

            min_contexts = len(call_contexts)
            for call in tool_calls:
                processed = await self._process_tool_call(
                    call,
                    provider,
                    messages,
                    call_contexts,
                    message=message,
                    context=context,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=runtime_metadata,
                    model_response=raw_result,
                )
                if isinstance(processed, StrategyResult):
                    return await self._finish_result(
                        processed,
                        message=message,
                        context=context,
                        provider=provider,
                        iteration_count=iteration_count,
                        model_call_count=model_call_count,
                        tokens_used=tokens_used,
                        started_at=started_at,
                        metadata=runtime_metadata,
                        model_response=raw_result,
                    )
                _, result = processed
                if call.tool_name == IS_DONE_TOOL_NAME:
                    decision = await self.middleware.after_iteration(
                        self._middleware_context(
                            MiddlewareHook.AFTER_ITERATION,
                            message=message,
                            context=context,
                            provider=provider,
                            iteration_count=iteration_count,
                            model_call_count=model_call_count,
                            tool_call_count=len(call_contexts),
                            tokens_used=tokens_used,
                            started_at=started_at,
                            metadata=runtime_metadata,
                            model_response=raw_result,
                        )
                    )
                    if decision.action is not MiddlewareAction.CONTINUE:
                        abort_result = self._middleware_abort_result(
                            decision,
                            iteration_count=iteration_count,
                            tokens_used=tokens_used,
                            contexts=call_contexts,
                        )
                        return await self._finish_result(
                            abort_result,
                            message=message,
                            context=context,
                            provider=provider,
                            iteration_count=iteration_count,
                            model_call_count=model_call_count,
                            tokens_used=tokens_used,
                            started_at=started_at,
                            metadata=runtime_metadata,
                            model_response=raw_result,
                        )
                    final = self._final_result(
                        output=result.output,
                        runner_metadata=runner_metadata,
                        contexts=call_contexts,
                        iteration_count=iteration_count,
                        tokens_used=tokens_used,
                        stop_reason=AgentStopReason.IS_DONE,
                    )
                    return await self._finish_result(
                        final,
                        message=message,
                        context=context,
                        provider=provider,
                        iteration_count=iteration_count,
                        model_call_count=model_call_count,
                        tokens_used=tokens_used,
                        started_at=started_at,
                        metadata=runtime_metadata,
                        model_response=raw_result,
                    )

            iteration_contexts = tuple(call_contexts[min_contexts:])
            decision = await self.middleware.after_iteration(
                self._middleware_context(
                    MiddlewareHook.AFTER_ITERATION,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tool_call_count=len(call_contexts),
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=runtime_metadata,
                    model_response=raw_result,
                )
            )
            if decision.action is not MiddlewareAction.CONTINUE:
                result = self._middleware_abort_result(
                    decision,
                    iteration_count=iteration_count,
                    tokens_used=tokens_used,
                    contexts=call_contexts,
                )
                return await self._finish_result(
                    result,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=runtime_metadata,
                    model_response=raw_result,
                )
            trace_count += self._append_reasoning_trace_if_needed(
                messages,
                request=message,
                iteration_count=iteration_count,
                assistant_output=None,
                current_iteration_contexts=iteration_contexts,
            )
            runtime_metadata["context_window_reasoning_trace_count"] = trace_count

    async def _invoke_with_middleware(
        self,
        runner: object,
        message: str,
        call_options: Mapping[str, Any],
        *,
        context: BaseAgentContext,
        provider: str,
        invoke_runner: Callable[..., Any],
        iteration_count: int,
        model_call_count: int,
        call_contexts: Sequence[ToolCallContext],
        tokens_used: int | None,
        started_at: float,
        metadata: Mapping[str, Any],
    ) -> tuple[object | StrategyResult, int]:
        """Invoke the runner, allowing middleware to retry model errors."""
        while True:
            decision = await self.middleware.before_model_call(
                self._middleware_context(
                    MiddlewareHook.BEFORE_MODEL_CALL,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tool_call_count=len(call_contexts),
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=metadata,
                )
            )
            if decision.action is not MiddlewareAction.CONTINUE:
                return (
                    self._middleware_abort_result(
                        decision,
                        iteration_count=iteration_count,
                        tokens_used=tokens_used,
                        contexts=call_contexts,
                    ),
                    model_call_count,
                )
            model_call_count += 1
            try:
                return await invoke_runner(runner, message, **dict(call_options)), model_call_count
            except Exception as exc:
                decision = await self.middleware.on_model_error(
                    self._middleware_context(
                        MiddlewareHook.ON_MODEL_ERROR,
                        message=message,
                        context=context,
                        provider=provider,
                        iteration_count=iteration_count,
                        model_call_count=model_call_count,
                        tool_call_count=len(call_contexts),
                        tokens_used=tokens_used,
                        started_at=started_at,
                        metadata=metadata,
                        error=exc,
                    )
                )
                if decision.action is MiddlewareAction.RETRY:
                    if decision.sleep_seconds:
                        await self.middleware.sleep(decision.sleep_seconds)
                    continue
                if decision.action is MiddlewareAction.ABORT_RUN:
                    return (
                        self._middleware_abort_result(
                            decision,
                            iteration_count=iteration_count,
                            tokens_used=tokens_used,
                            contexts=call_contexts,
                        ),
                        model_call_count,
                    )
                raise

    async def _finish_result(
        self,
        result: StrategyResult,
        *,
        message: str,
        context: BaseAgentContext,
        provider: str,
        iteration_count: int,
        model_call_count: int,
        tokens_used: int | None,
        started_at: float,
        metadata: Mapping[str, Any],
        model_response: object | None = None,
    ) -> StrategyResult:
        """Run after_run middleware and attach final middleware metadata."""
        decision = await self.middleware.after_run(
            self._middleware_context(
                MiddlewareHook.AFTER_RUN,
                message=message,
                context=context,
                provider=provider,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                tool_call_count=int(dict(result.metadata).get("tool_call_count", 0)),
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=metadata,
                model_response=model_response,
            )
        )
        if decision.action is MiddlewareAction.ABORT_RUN:
            result = self._middleware_abort_result(
                decision,
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                contexts=tuple(dict(result.metadata).get("tool_calls", ())),
            )
        result = self._with_middleware_metadata(result)
        merged_meta = {**dict(result.metadata), **dict(metadata)}
        result = StrategyResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata=merged_meta,
        )
        return result

    def _middleware_context(
        self,
        hook: MiddlewareHook,
        *,
        message: str,
        context: BaseAgentContext,
        provider: str,
        iteration_count: int,
        model_call_count: int,
        tool_call_count: int,
        tokens_used: int | None,
        started_at: float,
        metadata: Mapping[str, Any],
        tool_call: ToolCall | None = None,
        tool_result: ToolResult | None = None,
        model_response: object | None = None,
        error: BaseException | None = None,
        tool_is_internal: bool = False,
    ) -> MiddlewareContext:
        """Build a middleware context without adding metadata to the model prompt."""
        return MiddlewareContext(
            hook=hook,
            agent_name=self.agent_name,
            run_id=self.run_id,
            provider=provider,
            message=message,
            iteration_count=iteration_count,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
            elapsed_seconds=max(0, self.middleware.clock() - started_at),
            tokens_used=tokens_used,
            agent_context=context,
            tool_call=tool_call,
            tool_result=tool_result,
            model_response=model_response,
            error=error,
            tool_is_internal=tool_is_internal,
            metadata=dict(metadata),
        )

    def _middleware_abort_result(
        self,
        decision: MiddlewareDecision,
        *,
        iteration_count: int,
        tokens_used: int | None,
        contexts: Sequence[ToolCallContext],
    ) -> StrategyResult:
        """Return a controlled StrategyResult for middleware-aborted runs."""
        reason = decision.reason or "middleware_abort"
        return StrategyResult(
            output=f"Agent runtime stopped by middleware: {reason}",
            strategy_name="direct_runner",
            metadata={
                **self._runtime_metadata(
                    contexts=contexts,
                    iteration_count=iteration_count,
                    tokens_used=tokens_used,
                    stop_reason=AgentStopReason.MIDDLEWARE_ABORT,
                ),
                "middleware_abort_reason": reason,
                "middleware_decision": {
                    "action": decision.action.value,
                    "reason": decision.reason,
                    "metadata": dict(decision.metadata),
                },
            },
        )

    def _with_middleware_metadata(self, result: StrategyResult) -> StrategyResult:
        """Attach latest middleware metadata to a StrategyResult."""
        metadata = dict(result.metadata)
        metadata["middleware"] = self.middleware.metadata()
        return StrategyResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata=metadata,
        )

    async def execute_tool_call(self, call: ToolCall, *, provider: str) -> tuple[ToolCallContext, ToolResult]:
        """Resolve, authorize, validate, execute, and record one tool call."""
        try:
            tool = self._get_tool(call)
            spec = tool.spec()
            self._check_permission(spec, call)
            self._validate_tool_call(tool, call)
            result = await self._execute_tool(tool, call)
            state = ToolCallState.SUCCEEDED if result.status.value == "success" else ToolCallState.FAILED
        except ToolRegistryError as exc:
            result = ToolResult.error(call.tool_name, str(exc), metadata={"error": "unknown_tool", "detail": str(exc)})
            state = ToolCallState.FAILED
        except PermissionDeniedError as exc:
            permission = exc.details.get("permission", "")
            result = ToolResult.error(
                call.tool_name,
                str(exc),
                metadata={"error": "permission_denied", "permission": permission},
            )
            state = ToolCallState.DENIED
        except ToolExecutionError as exc:
            error_type = exc.details.get("error_type", type(exc).__name__)
            result = ToolResult.error(
                call.tool_name,
                str(exc),
                metadata={"error": "execution_error", "error_type": error_type},
            )
            state = ToolCallState.FAILED
        except Exception as exc:
            result = ToolResult.error(
                call.tool_name,
                f"Tool execution failed: {exc}",
                metadata={"error": "execution_error", "error_type": type(exc).__name__},
            )
            state = ToolCallState.FAILED

        return (
            ToolCallContext(
                tool_name=call.tool_name,
                arguments=call.arguments,
                state=state,
                call_id=call.call_id,
                result=result,
                provider=provider,
                metadata=dict(call.metadata),
            ),
            result,
        )

    @staticmethod
    def _middleware_denied_tool(
        call: ToolCall,
        provider: str,
        decision: MiddlewareDecision,
    ) -> tuple[ToolCallContext, ToolResult]:
        """Convert a deny_tool middleware decision into normal tool-call context."""
        result = ToolResult.error(
            call.tool_name,
            f"Tool denied by middleware: {decision.reason or 'middleware_denied'}",
            metadata={
                "error": "middleware_denied",
                "reason": decision.reason,
                **dict(decision.metadata),
            },
        )
        return (
            ToolCallContext(
                tool_name=call.tool_name,
                arguments=call.arguments,
                state=ToolCallState.DENIED,
                call_id=call.call_id,
                result=result,
                provider=provider,
                metadata=dict(call.metadata),
            ),
            result,
        )

    def _tool_is_internal(self, call: ToolCall) -> bool:
        """Return whether a call targets a runtime-only internal tool."""
        if call.tool_name == IS_DONE_TOOL_NAME:
            return True
        try:
            spec = self.tools._get(call.tool_name).spec()
        except Exception:
            return False
        metadata = getattr(spec, "metadata", {})
        return bool(isinstance(metadata, Mapping) and metadata.get("internal"))

    def _get_tool(self, call: ToolCall) -> object:
        """Resolve a tool from the catalog by name, raising ToolRegistryError if missing."""
        try:
            return self.tools._get(call.tool_name)
        except Exception as exc:
            raise ToolRegistryError(
                f"Tool '{call.tool_name}' is not registered.",
                details={"tool_name": call.tool_name, "error": str(exc)},
            ) from exc

    def _check_permission(self, spec: object, call: ToolCall) -> None:
        """Raise PermissionDeniedError when the policy rejects the call."""
        decision = self.permission_policy.check(spec, call)
        if decision is PermissionDecision.DENY:
            raise PermissionDeniedError(
                f"Permission denied for tool '{spec.name}' requiring {spec.permission.value}",
                details={"tool_name": spec.name, "permission": spec.permission.value},
            )

    def _validate_tool_call(self, tool: object, call: ToolCall) -> None:
        """Validate tool call arguments, raising ToolExecutionError on failure."""
        validation_error = tool.validate_call(call)
        if validation_error:
            raise ToolExecutionError(
                validation_error,
                details={"tool_name": call.tool_name, "error": "validation_error"},
            )

    async def _execute_tool(self, tool: object, call: ToolCall) -> ToolResult:
        """Execute the tool and return its result, raising ToolExecutionError on failure."""
        try:
            return await tool.execute(call)
        except Exception as exc:
            raise ToolExecutionError(
                f"Tool execution failed: {exc}",
                details={"tool_name": call.tool_name, "error_type": type(exc).__name__},
            ) from exc

    def _resolve_tool_schemas(self, provider: str) -> Sequence[dict[str, Any]]:
        """Return provider-native tool schemas when the toolkit is non-empty."""
        return self.tools.provider_schemas(provider) if len(self.tools) else ()

    @staticmethod
    def _extract_initial_messages(run_options: dict[str, Any]) -> list[dict[str, Any]]:
        """Pop and normalize the initial messages list from run options."""
        return [dict(item) for item in run_options.pop("messages", ())]

    def _build_iteration_call_options(
        self,
        run_options: dict[str, Any],
        context: BaseAgentContext,
        tool_schemas: Sequence[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Assemble per-iteration call options with system prompt, tools, and messages."""
        call_options = dict(run_options)
        call_options.setdefault("system", context.build_context())
        if tool_schemas:
            call_options.setdefault("tools", tool_schemas)
        if messages:
            call_options.setdefault("messages", tuple(messages))
        return call_options

    def _final_result(
        self,
        output: str,
        *,
        runner_metadata: dict[str, Any],
        contexts: Sequence[ToolCallContext],
        iteration_count: int,
        tokens_used: int | None,
        stop_reason: AgentStopReason,
    ) -> StrategyResult:
        """Build the final StrategyResult from an explicit runtime stop."""
        return StrategyResult(
            output=output,
            strategy_name="direct_runner",
            metadata={
                **self._runtime_metadata(
                    contexts=contexts,
                    iteration_count=iteration_count,
                    tokens_used=tokens_used,
                    stop_reason=stop_reason,
                ),
                **runner_metadata,
            },
        )

    async def _process_tool_call(
        self,
        call: ToolCall,
        provider: str,
        messages: list[dict[str, Any]],
        call_contexts: list[ToolCallContext],
        *,
        message: str,
        context: BaseAgentContext,
        iteration_count: int,
        model_call_count: int,
        tokens_used: int | None,
        started_at: float,
        metadata: Mapping[str, Any],
        model_response: object | None = None,
    ) -> tuple[ToolCallContext, ToolResult] | StrategyResult:
        """Execute one tool call, record its context, and append it to messages."""
        tool_is_internal = self._tool_is_internal(call)
        decision = await self.middleware.before_tool_call(
            self._middleware_context(
                MiddlewareHook.BEFORE_TOOL_CALL,
                message=message,
                context=context,
                provider=provider,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                tool_call_count=len(call_contexts),
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=metadata,
                tool_call=call,
                tool_is_internal=tool_is_internal,
                model_response=model_response,
            )
        )
        if decision.action is MiddlewareAction.ABORT_RUN:
            return self._middleware_abort_result(
                decision,
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                contexts=call_contexts,
            )
        if decision.action is MiddlewareAction.DENY_TOOL:
            context_record, result = self._middleware_denied_tool(call, provider, decision)
        else:
            context_record, result = await self.execute_tool_call(call, provider=provider)
        call_contexts.append(context_record)
        after_decision = await self.middleware.after_tool_call(
            self._middleware_context(
                MiddlewareHook.AFTER_TOOL_CALL,
                message=message,
                context=context,
                provider=provider,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                tool_call_count=len(call_contexts),
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=metadata,
                tool_call=call,
                tool_result=result,
                tool_is_internal=tool_is_internal,
                model_response=model_response,
            )
        )
        if after_decision.action is MiddlewareAction.ABORT_RUN:
            return self._middleware_abort_result(
                after_decision,
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                contexts=call_contexts,
            )
        if call.tool_name != IS_DONE_TOOL_NAME:
            visible_result = self.algorithm.model_visible_tool_result(call, result)
            messages.append(dict(ToolsFormatter.format_tool_result(call, visible_result, provider)))
        return context_record, result

    def _budget_stop(
        self,
        *,
        iteration_count: int,
        tokens_used: int | None,
        contexts: Sequence[ToolCallContext],
    ) -> StrategyResult | None:
        if self.config.max_iterations is not None and iteration_count >= self.config.max_iterations:
            return self._stopped_result(
                "Agent runtime stopped after reaching max_iterations.",
                stop_reason=AgentStopReason.MAX_ITERATIONS,
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                contexts=contexts,
            )
        if self.config.max_tokens is not None and tokens_used is not None and tokens_used >= self.config.max_tokens:
            return self._stopped_result(
                "Agent runtime stopped after reaching max_tokens.",
                stop_reason=AgentStopReason.MAX_TOKENS,
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                contexts=contexts,
            )
        return None

    def _stopped_result(
        self,
        output: str,
        *,
        stop_reason: AgentStopReason,
        iteration_count: int,
        tokens_used: int | None,
        contexts: Sequence[ToolCallContext],
    ) -> StrategyResult:
        return StrategyResult(
            output=output,
            strategy_name="direct_runner",
            metadata=self._runtime_metadata(
                contexts=contexts,
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                stop_reason=stop_reason,
            ),
        )

    def _runtime_metadata(
        self,
        *,
        contexts: Sequence[ToolCallContext],
        iteration_count: int,
        tokens_used: int | None,
        stop_reason: AgentStopReason,
    ) -> dict[str, Any]:
        return {
            "stop_reason": stop_reason.value,
            "iteration_count": iteration_count,
            "tokens_used": tokens_used,
            "tool_call_count": len(contexts),
            "tool_call_states": tuple(context.state.value for context in contexts),
            "tool_calls": tuple(contexts),
        }

    @staticmethod
    def _assistant_message(output: str) -> dict[str, Any]:
        return {"role": "assistant", "content": output}

    @staticmethod
    def _add_token_usage(current: int | None, delta: int | None) -> int | None:
        if delta is None:
            return current
        return (current or 0) + delta

    async def _prepare_algorithm_context(
        self,
        *,
        message: str,
        context: BaseAgentContext,
        runner: object,
        provider: str,
        invoke_runner: Callable[..., Any],
        runner_output_text: Callable[[object], str],
        runner_output_metadata: Callable[[object], Mapping[str, Any]],
        model_call_count: int,
        call_contexts: list[ToolCallContext],
        iteration_count: int,
        tokens_used: int | None,
        started_at: float,
        metadata: Mapping[str, Any],
    ) -> tuple[BaseAgentContext | StrategyResult, dict[str, Any] | None]:
        """Optionally create a plan artifact before the main execution loop."""
        if self.algorithm.plan_then_implement is None:
            return context, None
        plan_config = self.algorithm.plan_then_implement
        context_text = context.build_context()
        planner_prompt = build_plan_prompt(message, context_text, plan_config)
        try:
            raw_result, _ = await self._invoke_with_middleware(
                runner,
                message,
                {"system": planner_prompt},
                context=context,
                provider=provider,
                invoke_runner=invoke_runner,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                call_contexts=call_contexts,
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=metadata,
            )
        except Exception:
            if plan_config.fallback_on_empty:
                return self._plan_context_from_text(
                    fallback_plan(message),
                    message,
                    plan_config,
                    context,
                    fallback_used=True,
                ), {"context_window_plan_artifact": plan_config.artifact_name, "context_window_plan_fallback_used": True}
            raise
        if isinstance(raw_result, StrategyResult):
            return raw_result, None
        plan_text = runner_output_text(raw_result)
        fallback_used = False
        if not plan_text.strip():
            if not plan_config.fallback_on_empty:
                return context, {
                    "context_window_plan_artifact": plan_config.artifact_name,
                    "context_window_plan_fallback_used": False,
                }
            plan_text = fallback_plan(message)
            fallback_used = True
        return self._plan_context_from_text(
            plan_text,
            message,
            plan_config,
            context,
            fallback_used=fallback_used,
        ), {
            "context_window_plan_artifact": plan_config.artifact_name,
            "context_window_plan_fallback_used": fallback_used,
        }

    @staticmethod
    def _plan_context_from_text(
        plan_text: str,
        request: str,
        config: object,
        context: BaseAgentContext,
        *,
        fallback_used: bool = False,
    ) -> BaseAgentContext:
        """Attach a plan artifact to the context without adding a runner call."""
        artifact = plan_artifact_from_text(plan_text, request, config, fallback_used=fallback_used)
        return dataclasses.replace(context, artifacts=(*context.artifacts, artifact))

    def _append_reasoning_trace_if_needed(
        self,
        messages: list[dict[str, Any]],
        *,
        request: str,
        iteration_count: int,
        assistant_output: str | None,
        current_iteration_contexts: Sequence[ToolCallContext],
    ) -> int:
        """Append a reasoning trace message for the next model call if configured. Returns 1 if appended, 0 otherwise."""
        if self.algorithm.reasoning_trace is None:
            return 0
        trace_config = self.algorithm.reasoning_trace
        event = ContextWindowIterationEvent(
            request=request,
            iteration_count=iteration_count,
            assistant_output=assistant_output,
            tool_contexts=tuple(current_iteration_contexts),
        )
        trace_message = render_reasoning_trace(trace_config, event)
        messages.append({"role": trace_message.role, "content": trace_message.content})
        return 1
        event = ContextWindowIterationEvent(
            request=request,
            iteration_count=iteration_count,
            assistant_output=assistant_output,
            tool_contexts=tuple(current_iteration_contexts),
        )
        trace_message = render_reasoning_trace(trace_config, event)
        messages.append({"role": trace_message.role, "content": trace_message.content})
        return 1


__all__ = ["AgentRuntime"]
