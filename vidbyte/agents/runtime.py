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

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.types import AgentMessage
from vidbyte.context.algorithms import ContextWindowAlgorithm, ToolResultAdmission
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.context.runtime import ContextWindowPlacement, ContextWindowRunContext, InnerContextWindowAlgorithm
from vidbyte.context.window import ContextWindow
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot, AgentRuntimeConfig, AgentStopReason
from vidbyte.lib.dataclasses.middleware import MiddlewareAction, MiddlewareContext, MiddlewareDecision, MiddlewareHook
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.providers.output_schema import OutputSchemaFormatter
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import PermissionDeniedError, ToolExecutionError, ToolRegistryError
from vidbyte.lib.token_usage import token_usage_from_response
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.context.templates import NullRecorder, RecorderBase
from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase
from vidbyte.middleware import AgentMiddleware, MiddlewarePipeline
from vidbyte.middleware.builtins.context_compaction import ToolResultCompactionMiddleware
from vidbyte.prompts.agentic_loop import append_agentic_loop_prompt
from vidbyte.lib.dataclasses.context import BaseAgentContext, BaseContext
from vidbyte.lib.dataclasses.strategies import AgentResult
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
        tracer: TracerBase | None = None,
        middleware: Sequence[AgentMiddleware] = (),
        run_id: str | None = None,
        algorithm: ContextWindowAlgorithm | str | None = None,
        context_manager: ContextManager | None = None,
        recorder: RecorderBase | None = None,
        output_schema: type | Mapping[str, Any] | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.user_tools = tools
        self.tools = with_internal_agent_tools(tools)
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()
        self.run_id = run_id
        self.algorithm = ContextWindow.resolve_algorithm(algorithm)
        self._tracer: TracerBase = tracer or NullTracer()
        self.middleware = MiddlewarePipeline((*tuple(middleware), *self._context_window_admission_middleware()))
        self.context_manager = context_manager
        self.recorder: RecorderBase = recorder or NullRecorder()
        self.output_schema = output_schema
        self._schema_formatter = OutputSchemaFormatter()

    def _context_window_admission_middleware(self) -> tuple[AgentMiddleware, ...]:
        # Returns compatibility middleware for legacy tool-result admission presets.
        admission = ToolResultAdmission(self.algorithm.tool_result_admission)
        if admission is ToolResultAdmission.COMPACT:
            return (ToolResultCompactionMiddleware.truncate(max_chars=self.algorithm.max_tool_result_chars),)
        if admission is ToolResultAdmission.HIDE_RAW:
            return (ToolResultCompactionMiddleware.hide(),)
        return ()

    def build_context(
        self,
        message: str,
        *,
        base_context: BaseContext | None,
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
            run_metadata=dict(managed_context.run_metadata),
            tool_calls=(*tuple(managed_context.tool_calls), *tuple(existing_tool_calls)),
            responses=tuple(managed_context.responses),
            budget=managed_context.budget,
            artifacts=tuple(managed_context.artifacts),
            memory=managed_context.memory,
            permissions=managed_context.permissions,
            metadata=metadata,
            context_items=tuple(managed_context.context_items),
        )

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        """Run the direct model/tool loop until isDone or a budget stop."""
        algorithm_result = await AgentRuntimeContextAlgorithms(self).arun(
            message,
            handle=handle,
            context=context,
            metadata=metadata,
            options=options,
            trace_context=trace_context,
        )
        if algorithm_result is not None:
            return algorithm_result
        return await self._arun_once(
            message,
            handle=handle,
            context=context,
            metadata=metadata,
            options=options,
            trace_context=trace_context,
        )

    async def _arun_once(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        """Run one direct model/tool attempt until isDone or a budget stop."""
        provider = handle.provider
        run_options = dict(options or {})
        runtime_metadata = dict(metadata or {})
        inner_algorithm = AgentRuntimeContextAlgorithms(self).inner_loop_algorithm()
        if inner_algorithm is not None:
            if self.context_manager is None:
                self.context_manager = ContextManager()
            runtime_metadata["_inner_context_window_algorithm"] = inner_algorithm
            runtime_metadata["_context_window_state"] = {}
            # One run-start invocation lets the algorithm initialize before any iteration.
            await self._run_inner_context_window_hook(runtime_metadata, message=message, provider=provider)
        tool_schemas = self._resolve_tool_schemas(provider)
        messages = self._extract_initial_messages(run_options)
        call_contexts: list[ToolCallContext] = []
        iteration_count = 0
        model_call_count = 0
        tokens_used: int | None = None
        started_at = self.middleware.clock()
        last_response: object | None = None
        last_assistant_output: str | None = None
        run_state: dict[type, Any] = {}

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
                run_state=run_state,
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
                run_state=run_state,
            )

        while True:
            # Single inner-loop context-window point: after the prior iteration's tool calls finished.
            if iteration_count > 0:
                await self._run_inner_context_window_hook(
                    runtime_metadata,
                    message=message,
                    provider=provider,
                    iteration_count=iteration_count,
                    assistant_output=last_assistant_output,
                    call_contexts=call_contexts,
                    tokens_used=tokens_used,
                    runner=handle,
                    invoke_runner=self._invoke_context_window_runner,
                    runner_output_text=handle.extract_text,
                    runner_output_metadata=handle.extract_metadata,
                    options=run_options,
                    messages=messages,
                    system_prompt=self.system_prompt,
                )
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
                    run_state=run_state,
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
                    run_state=run_state,
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
                    run_state=run_state,
                    model_response=last_response,
                )

            call_options = self._build_iteration_call_options(run_options, context, tool_schemas, messages, provider)
            raw_result, model_call_count = await self._invoke_with_middleware(
                handle,
                message,
                call_options,
                context=context,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                call_contexts=call_contexts,
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=runtime_metadata,
                run_state=run_state,
                trace_context=trace_context,
            )
            if isinstance(raw_result, AgentResult):
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
                    run_state=run_state,
                    model_response=last_response,
                )
            last_response = raw_result
            iteration_count += 1
            last_assistant_output = handle.extract_text(raw_result)
            runner_metadata = dict(handle.extract_metadata(raw_result))
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
                    run_state=run_state,
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
                    run_state=run_state,
                    model_response=raw_result,
                )

            tool_calls = ToolsFormatter.parse_tool_calls(raw_result, provider)
            if not tool_calls:
                messages.append(self._assistant_message(handle.extract_text(raw_result)))
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
                        run_state=run_state,
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
                        run_state=run_state,
                        model_response=raw_result,
                    )
                continue

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
                    run_state=run_state,
                    model_response=raw_result,
                    trace_context=trace_context,
                )
                if isinstance(processed, AgentResult):
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
                        run_state=run_state,
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
                            run_state=run_state,
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
                            run_state=run_state,
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
                        run_state=run_state,
                        model_response=raw_result,
                    )

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
                    run_state=run_state,
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
                    run_state=run_state,
                    model_response=raw_result,
                )

    async def _invoke_with_middleware(self, handle: RunnerHandle, message: str, call_options: Mapping[str, Any], *, context: BaseAgentContext, iteration_count: int, model_call_count: int, call_contexts: Sequence[ToolCallContext], tokens_used: int | None, started_at: float, metadata: Mapping[str, Any], run_state: dict[type, Any] | None = None, trace_context: SpanContext | None = None) -> tuple[object | AgentResult, int]:
        """Invoke the runner, allowing middleware to retry model errors."""
        provider = handle.provider
        while True:
            current_call_options = dict(call_options)
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
                    run_state=run_state,
                    provider_messages=self._provider_messages_from_options(current_call_options),
                    system=str(current_call_options.get("system")) if current_call_options.get("system") is not None else None,
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
            current_call_options = self._apply_before_model_call_transform(current_call_options, decision)
            model_call_count += 1
            llm_span = self._tracer.start_span(
                "llm.call",
                parent=trace_context,
                **self._llm_trace_inputs(handle, message, current_call_options, provider, iteration_count, model_call_count, metadata),
            )
            try:
                raw_result = await handle.invoke(message, **current_call_options)
                output_text = handle.extract_text(raw_result)
                self._tracer.end_span(llm_span, output=output_text)
                return raw_result, model_call_count
            except Exception as exc:
                self._tracer.end_span(llm_span, error=exc)
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
                        run_state=run_state,
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
        result: AgentResult,
        *,
        message: str,
        context: BaseAgentContext,
        provider: str,
        iteration_count: int,
        model_call_count: int,
        tokens_used: int | None,
        started_at: float,
        metadata: Mapping[str, Any],
        run_state: dict[type, Any] | None = None,
        model_response: object | None = None,
    ) -> AgentResult:
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
                run_state=run_state,
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
        result = self._with_context_window_metadata(result, metadata)
        result = self._with_run_state_metadata(result, run_state)
        return self._with_middleware_metadata(result)

    @staticmethod
    def _with_run_state_metadata(result: AgentResult, run_state: dict[type, Any] | None) -> AgentResult:
        """Merge per-run metadata published by middleware (e.g. trace artifacts) into the result."""
        # Generic, feature-agnostic lift of run_state["__result_metadata__"]; no feature imports here.
        published = (run_state or {}).get("__result_metadata__")
        if not isinstance(published, Mapping) or not published:
            return result
        metadata = {**dict(result.metadata), **dict(published)}
        return AgentResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata=metadata,
            structured=result.structured,
        )

    async def _run_inner_context_window_hook(self, metadata: Mapping[str, Any], *, message: str, provider: str, iteration_count: int = 0, assistant_output: str | None = None, call_contexts: Sequence[ToolCallContext] = (), tokens_used: int | None = None, runner: object | None = None, invoke_runner: Callable[..., Any] | None = None, runner_output_text: Callable[[object], str] | None = None, runner_output_metadata: Callable[[object], Mapping[str, Any]] | None = None, options: Mapping[str, Any] | None = None, messages: Sequence[dict[str, Any]] | None = None, system_prompt: str | None = None) -> None:
        """Build the slim run context and invoke the inner-loop algorithm's single hook."""
        # Called once at run start (no iteration) and once after each completed iteration's tool calls.
        algorithm = metadata.get("_inner_context_window_algorithm")
        state = metadata.get("_context_window_state")
        if not isinstance(algorithm, InnerContextWindowAlgorithm) or not isinstance(state, dict):
            return
        if self.context_manager is None:
            return
        iteration = None
        if iteration_count > 0:
            iteration = self._iteration_snapshot(
                message=message,
                provider=provider,
                iteration_count=iteration_count,
                assistant_output=assistant_output,
                call_contexts=call_contexts,
                tokens_used=tokens_used,
                metadata=metadata,
            )
        await algorithm.after_tool_calls(
            ContextWindowRunContext(
                context_manager=self.context_manager,
                recorder=self.recorder,
                state=state,
                iteration=iteration,
                runner=runner,
                provider=provider,
                invoke_runner=invoke_runner,
                runner_output_text=runner_output_text,
                runner_output_metadata=runner_output_metadata,
                options=options,
                messages=messages,
                system_prompt=system_prompt,
            )
        )

    @staticmethod
    async def _invoke_context_window_runner(runner: object, prompt: str, **options: Any) -> object:
        """Invoke the current RunnerHandle for an inner-loop context-window algorithm."""
        if not isinstance(runner, RunnerHandle):
            raise TypeError("Inner context-window runner must be a RunnerHandle.")
        return await runner.invoke(prompt, **options)

    @staticmethod
    def _iteration_snapshot(*, message: str, provider: str, iteration_count: int, assistant_output: str | None, call_contexts: Sequence[ToolCallContext], tokens_used: int | None, metadata: Mapping[str, Any]) -> AgentIterationSnapshot:
        """Build an observable direct-runtime iteration snapshot."""
        # Excludes private lifecycle objects and raw provider responses from snapshot metadata.
        safe_metadata = {key: value for key, value in dict(metadata).items() if not str(key).startswith("_")}
        return AgentIterationSnapshot(
            iteration_count=iteration_count,
            message=message,
            provider=provider,
            assistant_output=assistant_output,
            tool_calls=tuple(call_contexts),
            tokens_used=tokens_used,
            metadata=safe_metadata,
        )

    @staticmethod
    def _with_context_window_metadata(result: AgentResult, metadata: Mapping[str, Any]) -> AgentResult:
        """Attach public context-window metadata produced by inner-loop algorithms."""
        # Copies only public metadata keys and leaves private runtime state out of the result.
        state = metadata.get("_context_window_state")
        if not isinstance(state, dict):
            return result
        public_metadata = {key: value for key, value in state.items() if not str(key).startswith("_")}
        if not public_metadata:
            return result
        result_metadata = {**dict(result.metadata), **public_metadata}
        return AgentResult(output=result.output, strategy_name=result.strategy_name, calls=result.calls, metadata=result_metadata, structured=result.structured)

    def _apply_before_model_call_transform(self, call_options: Mapping[str, Any], decision: MiddlewareDecision) -> dict[str, Any]:
        # Returns call options with any before-model-call transform applied.
        transformed = dict(call_options)
        transform = decision.transform
        if transform is None:
            return transformed
        if transform.system is not None:
            transformed["system"] = transform.system
        if transform.provider_messages is not None:
            transformed["messages"] = tuple(dict(message) for message in transform.provider_messages)
        return transformed

    def _provider_messages_from_options(self, call_options: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        # Extracts provider messages from runner call options as immutable mapping copies.
        raw_messages = call_options.get("messages", ())
        if not isinstance(raw_messages, Sequence) or isinstance(raw_messages, (str, bytes)):
            return ()
        return tuple(dict(message) for message in raw_messages if isinstance(message, Mapping))

    def _llm_trace_inputs(self, handle: RunnerHandle, message: str, call_options: Mapping[str, Any], provider: str, iteration_count: int, model_call_count: int, metadata: Mapping[str, Any]) -> dict[str, Any]:
        # Builds sanitized, inspectable model-call inputs for trace providers.
        system = call_options.get("system")
        messages = self._provider_messages_from_options(call_options)
        tools = tuple(call_options.get("tools", ()) or ())
        inputs: dict[str, Any] = {
            "agent_name": self.agent_name,
            "provider": provider,
            "model": self._runner_model_name(handle.runner),
            "iteration": iteration_count,
            "model_call": model_call_count,
            "prompt": self._safe_trace_value(message),
            "metadata": self._safe_trace_value(metadata),
            "input_messages": self._safe_trace_value(self._provider_visible_trace_messages(system, messages, message)),
        }
        if system is not None:
            inputs["system"] = self._safe_trace_value(str(system))
        if messages:
            inputs["messages"] = self._safe_trace_value(messages)
        if tools:
            inputs["tool_count"] = len(tools)
            inputs["tool_names"] = tuple(str(tool.get("name") or tool.get("function", {}).get("name") or "") for tool in tools if isinstance(tool, Mapping))
        return inputs

    def _provider_visible_trace_messages(self, system: object | None, messages: Sequence[Mapping[str, Any]], prompt: str) -> tuple[Mapping[str, Any], ...]:
        # Mirrors the provider-visible message order for trace inspection.
        visible: list[Mapping[str, Any]] = []
        if system is not None:
            visible.append({"role": "system", "content": str(system)})
        visible.extend(dict(message) for message in messages)
        visible.append({"role": "user", "content": prompt})
        return tuple(visible)

    @staticmethod
    def _runner_model_name(runner: object) -> str | None:
        # Extracts a best-effort model name from common SDK runner shapes.
        config = getattr(runner, "_config", None)
        model = getattr(config, "model", None)
        if model is not None:
            return str(model)
        model_name = getattr(runner, "model_name", None)
        if callable(model_name):
            try:
                return str(model_name())
            except Exception:
                return None
        return str(model_name) if model_name is not None else None

    @classmethod
    def _safe_trace_value(cls, value: Any) -> Any:
        # Recursively removes secret-like mapping keys from trace inputs.
        if isinstance(value, Mapping):
            return {key: cls._safe_trace_value(item) for key, item in value.items() if not cls._is_secret_trace_key(str(key))}
        if isinstance(value, tuple):
            return tuple(cls._safe_trace_value(item) for item in value)
        if isinstance(value, list):
            return [cls._safe_trace_value(item) for item in value]
        return value

    @staticmethod
    def _is_secret_trace_key(key: str) -> bool:
        # Identifies credential-like keys that must not be sent to trace providers.
        upper = key.upper()
        return any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH"))

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
        run_state: dict[type, Any] | None = None,
        tool_call: ToolCall | None = None,
        tool_result: ToolResult | None = None,
        model_response: object | None = None,
        error: BaseException | None = None,
        tool_is_internal: bool = False,
        provider_messages: Sequence[Mapping[str, Any]] = (),
        system: str | None = None,
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
            provider_messages=tuple(provider_messages),
            system=system,
            tool_is_internal=tool_is_internal,
            metadata=dict(metadata),
            run_state=run_state if run_state is not None else {},
        )

    def _middleware_abort_result(
        self,
        decision: MiddlewareDecision,
        *,
        iteration_count: int,
        tokens_used: int | None,
        contexts: Sequence[ToolCallContext],
    ) -> AgentResult:
        """Return a controlled AgentResult for middleware-aborted runs."""
        reason = decision.reason or "middleware_abort"
        return AgentResult(
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

    def _with_middleware_metadata(self, result: AgentResult) -> AgentResult:
        """Attach latest middleware metadata to a AgentResult."""
        metadata = dict(result.metadata)
        metadata["middleware"] = self.middleware.metadata()
        return AgentResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata=metadata,
            structured=result.structured,
        )

    async def execute_tool_call(
        self,
        call: ToolCall,
        *,
        provider: str,
        trace_context: SpanContext | None = None,
    ) -> tuple[ToolCallContext, ToolResult]:
        """Resolve, authorize, validate, execute, and record one tool call."""
        tool_span = self._tracer.start_span(
            "tool.call",
            parent=trace_context,
            tool_name=call.tool_name,
        )
        try:
            tool = self._get_tool(call)
            spec = tool.spec()
            self._check_permission(spec, call)
            self._validate_tool_call(tool, call)
            result = await self._execute_tool(tool, call)
            if spec.output_schema is not None and result.status.value == "success":
                _, error = self._schema_formatter.validate(result.output, spec.output_schema)
                if error:
                    result = ToolResult.error(
                        call.tool_name,
                        f"tool call error: output shape mismatch: {error}",
                        metadata={"error": "output_schema_violation", "detail": error},
                    )
            state = ToolCallState.SUCCEEDED if result.status.value == "success" else ToolCallState.FAILED
            self._tracer.end_span(tool_span, output=result.output)
        except ToolRegistryError as exc:
            result = ToolResult.error(call.tool_name, str(exc), metadata={"error": "unknown_tool", "detail": str(exc)})
            state = ToolCallState.FAILED
            self._tracer.end_span(tool_span, error=exc)
        except PermissionDeniedError as exc:
            permission = exc.details.get("permission", "")
            result = ToolResult.error(
                call.tool_name,
                str(exc),
                metadata={"error": "permission_denied", "permission": permission},
            )
            state = ToolCallState.DENIED
            self._tracer.end_span(tool_span, error=exc)
        except ToolExecutionError as exc:
            error_type = exc.details.get("error_type", type(exc).__name__)
            result = ToolResult.error(
                call.tool_name,
                str(exc),
                metadata={"error": "execution_error", "error_type": error_type},
            )
            state = ToolCallState.FAILED
            self._tracer.end_span(tool_span, error=exc)
        except Exception as exc:
            result = ToolResult.error(
                call.tool_name,
                f"Tool execution failed: {exc}",
                metadata={"error": "execution_error", "error_type": type(exc).__name__},
            )
            state = ToolCallState.FAILED
            self._tracer.end_span(tool_span, error=exc)

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

    def _build_iteration_call_options(self, run_options: dict[str, Any], context: BaseAgentContext, tool_schemas: Sequence[dict[str, Any]], messages: list[dict[str, Any]], provider: str = "") -> dict[str, Any]:
        """Assemble per-iteration call options with system prompt, primitives zone, tools, messages, and response format."""
        call_options = dict(run_options)
        system = self._build_system_string(context)
        call_options.setdefault("system", system)
        if tool_schemas:
            call_options.setdefault("tools", tool_schemas)
        conversation_messages = self._build_conversation_messages(messages)
        if conversation_messages:
            call_options.setdefault("messages", conversation_messages)
        if self.output_schema is not None:
            fmt = self._schema_formatter.build_response_format(provider, self.output_schema)
            if fmt is not None:
                call_options.setdefault("response_format", fmt)
        return call_options

    def _build_conversation_messages(self, messages: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
        """Assemble placed context-window conversation messages around runtime messages."""
        # Preserves existing runtime messages while adding explicit conversation placements.
        if self.context_manager is None:
            return tuple(messages)
        top = self.context_manager.render_conversation_messages(ContextWindowPlacement.TOP_OF_CONVERSATION)
        end = self.context_manager.render_conversation_messages(ContextWindowPlacement.END_OF_CONVERSATION)
        return (*top, *tuple(messages), *end)

    def _build_system_string(self, context: BaseAgentContext) -> str:
        """Assemble the system string with fixed header, primitives zone, and body in order."""
        fixed = context.build_context_fixed()
        primitives_zone = self.context_manager.render_primitives_zone() if self.context_manager else ""
        body = context.build_context_body()
        parts = [p for p in (fixed, primitives_zone, body) if p]
        return "\n\n".join(parts)

    def _final_result(
        self,
        output: str,
        *,
        runner_metadata: dict[str, Any],
        contexts: Sequence[ToolCallContext],
        iteration_count: int,
        tokens_used: int | None,
        stop_reason: AgentStopReason,
    ) -> AgentResult:
        """Build the final AgentResult, populating structured when output_schema is set."""
        structured: Any = None
        if self.output_schema is not None:
            structured, _ = self._schema_formatter.validate(output, self.output_schema)
        return AgentResult(
            output=output,
            strategy_name="direct_runner",
            structured=structured,
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
        run_state: dict[type, Any] | None = None,
        model_response: object | None = None,
        trace_context: SpanContext | None = None,
    ) -> tuple[ToolCallContext, ToolResult] | AgentResult:
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
                run_state=run_state,
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
            context_record, result = await self.execute_tool_call(call, provider=provider, trace_context=trace_context)
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
                run_state=run_state,
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
            visible_result = self._apply_primitive_binding(call, result)
            if visible_result is result and after_decision.transform is not None and after_decision.transform.model_visible_tool_result is not None:
                visible_result = after_decision.transform.model_visible_tool_result
            messages.append(dict(ToolsFormatter.format_tool_result(call, visible_result, provider)))
        return context_record, result

    def _apply_primitive_binding(self, call: ToolCall, result: ToolResult) -> ToolResult:
        """Route a successful tool result into its bound primitive and return an acknowledgment result."""
        if self.context_manager is None or result.status.value != "success":
            return result
        try:
            tool_obj = self.tools._get(call.tool_name)
            spec = tool_obj.spec()
        except Exception:
            return result
        primitive_id = getattr(spec, "binds_to_primitive", None)
        if not primitive_id:
            return result
        from vidbyte.context.primitives import TextContextItem
        new_primitive = TextContextItem(
            primitive_id=primitive_id,
            title=f"Tool: {call.tool_name}",
            content=result.output,
            source=call.tool_name,
        )
        try:
            self.context_manager.upsert(new_primitive)
        except ValueError:
            return result
        from vidbyte.tools.types import ToolResult as TR
        return TR.success(
            result.tool_name,
            f"[Output of '{call.tool_name}' stored in primitive '{primitive_id}']",
            metadata={**dict(result.metadata), "primitive_id": primitive_id},
        )

    def _budget_stop(
        self,
        *,
        iteration_count: int,
        tokens_used: int | None,
        contexts: Sequence[ToolCallContext],
    ) -> AgentResult | None:
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
    ) -> AgentResult:
        return AgentResult(
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


__all__ = ["AgentRuntime"]

