"""Context Protocol Header

Description:
    Defines the internal direct execution runtime for Vidbyte agents.
Purpose:
    Keeps agent loop execution, context-window construction, tool execution,
    permission checks, provider-reported token accounting, and exact internal-tool
    exposure policy out of BaseAgent.
Architecture:
    - AgentRuntime: Builds BaseAgentContext and runs direct model/tool loops.
    - include_internal_tools: Defaults to current behavior but lets isolated child
      runtimes expose exactly their explicitly supplied tool catalog.
Relations:
    Used by vidbyte.agents.base. Depends on shared context, tool, security, and
    strategy dataclasses without owning modality routing or runner construction.
    Review algorithms may disable implicit internal tools while ordinary agents
    retain them through the default constructor behavior.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidbyte.agents.fallback import AgentFallback, FallbackTransform
    from vidbyte.agents.settings.tool import ToolSettings

from vidbyte.agents.context_algorithms import AgentRuntimeContextAlgorithms
from vidbyte.agents.fallback.policies import FallbackSignals
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
from vidbyte.lib.errors import AllModelsFailedError, PermissionDeniedError, ToolExecutionError, ToolRegistryError
from vidbyte.lib.token_usage import token_usage_from_response
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.agents.pricing import UsageTracker
from vidbyte.context.templates import NullRecorder, RecorderBase
from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase
from vidbyte.middleware import AgentMiddleware, MiddlewarePipeline
from vidbyte.middleware.builtins.context_compaction import ToolResultCompactionMiddleware
from vidbyte.prompts.agentic_loop import append_agentic_loop_prompt
from vidbyte.agents.contract import AgentLoopSettingsOutputContract
from vidbyte.agents.contracts.schema import SchemaConformance
from vidbyte.lib.dataclasses.context import BaseAgentContext, BaseContext
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.tools._internal import IS_DONE_TOOL_NAME, with_internal_agent_tools
from vidbyte.tools.activity import ActivityToolFormatter
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionDecision, PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolCallContext, ToolCallState, ToolResult


class AgentRuntime:
    """Internal runtime for direct agent execution."""

    def __init__(self, *, agent_name: str, system_prompt: str, tools: Tools, permission_policy: PermissionPolicy, config: AgentRuntimeConfig | None = None, tracer: TracerBase | None = None, middleware: Sequence[AgentMiddleware] = (), run_id: str | None = None, algorithm: ContextWindowAlgorithm | str | None = None, context_manager: ContextManager | None = None, recorder: RecorderBase | None = None, output_schema: type | Mapping[str, Any] | None = None, output_contract: "AgentLoopSettingsOutputContract | None" = None, include_internal_tools: bool = True, usage_tracker: UsageTracker | None = None, fallback: "AgentFallback | None" = None) -> None:
        # Configure one direct runtime; isolated review child runtimes may disable implicit internal tools.
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.user_tools = tools
        self.tools = with_internal_agent_tools(tools) if include_internal_tools else tools
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
        self._wire_schema_cache: dict[str, Any] | None = None
        self.output_contract = output_contract or AgentLoopSettingsOutputContract(())
        self.usage_tracker = usage_tracker or UsageTracker()
        self.fallback = fallback

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
        rejections = 0
        compaction_count = 0
        tokens_used: int | None = None
        started_at = self.middleware.clock()
        last_response: object | None = None
        last_assistant_output: str | None = None
        run_state: dict[type, Any] = {}
        iteration_outputs: list[str] = []
        active_trace_context = trace_context
        fallback_index = 0
        fallback_attempts: list[dict[str, str]] = []
        fallback_errors: list[BaseException] = []

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

            if self.fallback is not None and iteration_count > 0:
                checkpoint_transition = self._checkpoint_fallback_transition(
                    index=fallback_index,
                    handle=handle,
                    provider=provider,
                    messages=messages,
                    attempts=fallback_attempts,
                    parent_span=trace_context,
                )
                if checkpoint_transition is not None:
                    handle, provider = checkpoint_transition.handle, checkpoint_transition.provider
                    tool_schemas, messages = checkpoint_transition.tool_schemas, checkpoint_transition.messages
                    fallback_index = checkpoint_transition.index
                    self._publish_fallback_metadata(
                        run_state,
                        self.fallback.result_metadata(fallback_attempts, context_reset=checkpoint_transition.context_reset),
                    )

            if self.fallback is not None and iteration_count > 0:
                loop_transition = self._loop_fallback_transition(
                    index=fallback_index,
                    handle=handle,
                    provider=provider,
                    messages=messages,
                    call_contexts=call_contexts,
                    attempts=fallback_attempts,
                    parent_span=trace_context,
                )
                if loop_transition is not None:
                    handle, provider = loop_transition.handle, loop_transition.provider
                    tool_schemas, messages = loop_transition.tool_schemas, loop_transition.messages
                    fallback_index = loop_transition.index
                    self._publish_fallback_metadata(
                        run_state,
                        self.fallback.result_metadata(fallback_attempts, context_reset=loop_transition.context_reset),
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

            iteration_span = self._start_semantic_span(
                "runtime.iteration",
                parent=trace_context,
                agent_name=self.agent_name,
                iteration=iteration_count,
                model_call_count=model_call_count,
                tool_call_count=len(call_contexts),
                tokens_used=tokens_used,
            )
            active_trace_context = iteration_span or trace_context
            call_options = self._build_iteration_call_options(
                run_options,
                context,
                tool_schemas,
                messages,
                provider,
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                tool_call_count=len(call_contexts),
            )
            try:
                raw_result, model_call_count, compaction_count = await self._invoke_with_middleware(
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
                    trace_context=active_trace_context,
                    compaction_count=compaction_count,
                    timeout_seconds=self.fallback.deadline_for(fallback_index) if self.fallback is not None else None,
                )
            except BaseException as exc:
                self._end_semantic_span(iteration_span, error=exc)
                transition = self._fallback_transition(
                    exc,
                    index=fallback_index,
                    handle=handle,
                    provider=provider,
                    messages=messages,
                    attempts=fallback_attempts,
                    errors=fallback_errors,
                    parent_span=trace_context,
                )
                if transition is None:
                    raise
                handle, provider = transition.handle, transition.provider
                tool_schemas, messages = transition.tool_schemas, transition.messages
                fallback_index = transition.index
                # A non-None transition proves self.fallback is set, so this needs no further guard.
                self._publish_fallback_metadata(
                    run_state,
                    self.fallback.result_metadata(fallback_attempts, context_reset=transition.context_reset),
                )
                continue
            self._end_semantic_span(iteration_span, output=handle.extract_text(raw_result))
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
            iteration_outputs.append(last_assistant_output or "")
            run_state["__iteration_outputs__"] = tuple(iteration_outputs)
            runner_metadata = dict(handle.extract_metadata(raw_result))
            tokens_used = self._add_token_usage(tokens_used, token_usage_from_response(raw_result, runner_metadata))
            usage_record = self.usage_tracker.record_call(raw_result)

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
                    model_usage=usage_record.usage if usage_record is not None else None,
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
            self._record_parser_span(
                "parser.tool_calls",
                parent=active_trace_context,
                provider=provider,
                tool_call_count=len(tool_calls),
            )
            if not tool_calls:
                if self.config.max_tokens is not None and tokens_used is not None and tokens_used >= self.config.max_tokens:
                    token_stop = self._stopped_result(
                        "Agent runtime stopped after reaching max_tokens.",
                        stop_reason=AgentStopReason.MAX_TOKENS,
                        iteration_count=iteration_count,
                        tokens_used=tokens_used,
                        contexts=call_contexts,
                    )
                    return await self._finish_result(
                        token_stop,
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
                if self.output_contract.active():
                    counters = self._contract_counters(iteration_count=iteration_count, model_call_count=model_call_count, call_contexts=call_contexts, tokens_used=tokens_used, started_at=started_at, final_output=last_assistant_output, compaction_count=compaction_count)
                    self._publish_contract_evaluations(run_state, counters)
                    unmet = self.output_contract.unmet(counters)
                    if unmet and self.output_contract.exhausted(rejections):
                        return await self._finish_result(
                            self._stopped_result(last_assistant_output or "", stop_reason=AgentStopReason.CONTRACT_UNSATISFIED, iteration_count=iteration_count, tokens_used=tokens_used, contexts=call_contexts),
                            message=message, context=context, provider=provider, iteration_count=iteration_count, model_call_count=model_call_count, tokens_used=tokens_used, started_at=started_at, metadata=runtime_metadata, run_state=run_state, model_response=raw_result,
                        )
                    if unmet:
                        rejections += 1
                        messages.append({"role": "user", "content": self.output_contract.feedback(unmet, counters)})
                        continue
                final = self._final_result(
                    output=last_assistant_output,
                    runner_metadata=runner_metadata,
                    contexts=call_contexts,
                    iteration_count=iteration_count,
                    tokens_used=tokens_used,
                    stop_reason=AgentStopReason.FINAL_RESPONSE,
                )
                if inner_algorithm is not None:
                    messages.append(self._assistant_message(last_assistant_output))
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
                if inner_algorithm is not None and decision.action is MiddlewareAction.CONTINUE:
                    continue
                if decision.action is not MiddlewareAction.CONTINUE:
                    final = self._middleware_abort_result(
                        decision,
                        iteration_count=iteration_count,
                        tokens_used=tokens_used,
                        contexts=call_contexts,
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

            assistant_tool_msg = ToolsFormatter.format_assistant_tool_calls(raw_result, provider)
            if assistant_tool_msg is not None:
                messages.append(dict(assistant_tool_msg))
            contract_rejected = False
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
                    trace_context=active_trace_context,
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
                    if self.output_contract.active():
                        counters = self._contract_counters(iteration_count=iteration_count, model_call_count=model_call_count, call_contexts=call_contexts, tokens_used=tokens_used, started_at=started_at, final_output=result.output, compaction_count=compaction_count)
                        self._publish_contract_evaluations(run_state, counters)
                        unmet = self.output_contract.unmet(counters)
                        if unmet and self.output_contract.exhausted(rejections):
                            return await self._finish_result(
                                self._stopped_result(result.output or "", stop_reason=AgentStopReason.CONTRACT_UNSATISFIED, iteration_count=iteration_count, tokens_used=tokens_used, contexts=call_contexts),
                                message=message, context=context, provider=provider, iteration_count=iteration_count, model_call_count=model_call_count, tokens_used=tokens_used, started_at=started_at, metadata=runtime_metadata, run_state=run_state, model_response=raw_result,
                            )
                        if unmet:
                            rejections += 1
                            self._append_tool_result_message(messages, call, ToolResult.error(call.tool_name, self.output_contract.feedback(unmet, counters)), provider, MiddlewareDecision.continue_())
                            contract_rejected = True
                            break
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

            if contract_rejected:
                continue

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

    async def _invoke_with_middleware(self, handle: RunnerHandle, message: str, call_options: Mapping[str, Any], *, context: BaseAgentContext, iteration_count: int, model_call_count: int, call_contexts: Sequence[ToolCallContext], tokens_used: int | None, started_at: float, metadata: Mapping[str, Any], run_state: dict[type, Any] | None = None, trace_context: SpanContext | None = None, compaction_count: int = 0, timeout_seconds: float | None = None) -> tuple[object | AgentResult, int, int]:
        """Invoke the runner, allowing middleware to retry model errors while tracking compaction events."""
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
                    compaction_count,
                )
            compaction_count += self._compaction_event_delta(decision)
            current_call_options = self._apply_before_model_call_transform(current_call_options, decision)
            model_call_count += 1
            llm_span = self._tracer.start_span(
                "llm.call",
                parent=trace_context,
                **self._llm_trace_inputs(
                    handle,
                    message=message,
                    call_options=current_call_options,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    metadata=metadata,
                ),
            )
            try:
                if timeout_seconds is not None:
                    raw_result = await asyncio.wait_for(handle.invoke(message, **current_call_options), timeout=timeout_seconds)
                else:
                    raw_result = await handle.invoke(message, **current_call_options)
                output_text = handle.extract_text(raw_result)
                self._tracer.end_span(llm_span, output=output_text)
                return raw_result, model_call_count, compaction_count
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
                        compaction_count,
                    )
                raise
            except BaseException as exc:
                # Catches CancelledError and other BaseException subclasses so the
                # llm.call span is always finalized before propagating.
                self._tracer.end_span(llm_span, error=exc)
                raise

    def _fallback_transition(self, error: BaseException, *, index: int, handle: RunnerHandle, provider: str, messages: list[dict[str, Any]], attempts: list[dict[str, str]], errors: list[BaseException], parent_span: SpanContext | None) -> "FallbackTransform | None":
        """Return rebuilt state for the next model in the chain, or None when the caller must re-raise."""
        if self.fallback is None or not self.fallback.is_model_error(error):
            return None
        next_index = self.fallback.advance(error, index)
        if next_index is None:
            self._raise_chain_exhausted(error, attempts=attempts, errors=errors)
            return None
        errors.append(error)
        attempts.append(self.fallback.attempt_record(index, next_index, error))
        transition = self.fallback.transform(handle, provider, self.tools, messages, next_index)
        self._record_fallback_span(attempts[-1], transition.context_reset, parent_span)
        return transition

    def _checkpoint_fallback_transition(self, *, index: int, handle: RunnerHandle, provider: str, messages: list[dict[str, Any]], attempts: list[dict[str, str]], parent_span: SpanContext | None) -> "FallbackTransform | None":
        # Returns rebuilt state when the checkpoint vote elects to downgrade, or None to keep the current model.
        rollup = self.usage_tracker.rollup()
        decision = self.fallback.advance_after_checkpoint(
            index,
            signals=FallbackSignals(cost_usd=rollup.cost_usd, total_tokens=rollup.total_tokens),
        )
        if decision is None:
            return None
        next_index, reason = decision
        record = self.fallback.policy_attempt_record(index, next_index, reason)
        attempts.append(record)
        transition = self.fallback.transform(handle, provider, self.tools, messages, next_index)
        self._record_fallback_span(record, transition.context_reset, parent_span)
        return transition

    def _loop_fallback_transition(self, *, index: int, handle: RunnerHandle, provider: str, messages: list[dict[str, Any]], call_contexts: Sequence[ToolCallContext], attempts: list[dict[str, str]], parent_span: SpanContext | None) -> "FallbackTransform | None":
        # Returns rebuilt state when a tool-call-loop policy detects a stuck pattern, or None to keep the current model.
        next_index = self.fallback.advance_after_loop_detected(index, call_contexts)
        if next_index is None:
            return None
        record = self.fallback.policy_attempt_record(index, next_index, "tool_call_loop_detected")
        attempts.append(record)
        transition = self.fallback.transform(handle, provider, self.tools, messages, next_index)
        self._record_fallback_span(record, transition.context_reset, parent_span)
        return transition

    def _raise_chain_exhausted(self, error: BaseException, *, attempts: Sequence[Mapping[str, str]], errors: Sequence[BaseException]) -> None:
        # Only a spent chain becomes AllModelsFailedError; a chain that never switched re-raises untouched.
        if not attempts:
            return
        raise AllModelsFailedError(
            f"Agent '{self.agent_name}' exhausted its fallback chain after {len(attempts)} model switch(es).",
            attempts=attempts,
            errors=[*errors, error],
        ) from errors[0]

    def _record_fallback_span(self, attempt: Mapping[str, str], context_reset: bool, parent_span: SpanContext | None) -> None:
        # Records a short span so a model switch is visible without diffing llm.call spans.
        span = self._start_semantic_span(
            "agent.fallback",
            parent=parent_span,
            agent_name=self.agent_name,
            **{key: str(value) for key, value in attempt.items()},
            context_reset=context_reset,
        )
        self._end_semantic_span(span, output=str(attempt.get("to", "")))

    @staticmethod
    def _publish_fallback_metadata(run_state: dict[type, Any], record: Mapping[str, Any]) -> None:
        # Publishes the switch log through the generic run_state channel _with_run_state_metadata already lifts.
        published = run_state.get("__result_metadata__")
        base = dict(published) if isinstance(published, Mapping) else {}
        run_state["__result_metadata__"] = {**base, "fallback": dict(record)}

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
        iteration_outputs = (run_state or {}).get("__iteration_outputs__")
        extra: dict[str, Any] = {}
        if isinstance(published, Mapping) and published:
            extra.update(published)
        if iteration_outputs is not None:
            extra["iteration_outputs"] = iteration_outputs
        if not extra:
            return result
        metadata = {**dict(result.metadata), **extra}
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
        algorithm_span = self._start_semantic_span(
            f"algorithm.{getattr(algorithm, 'name', algorithm.__class__.__name__)}",
            message=message,
            provider=provider,
            iteration=iteration_count,
        )
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
        try:
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
            self._end_semantic_span(algorithm_span, output="completed")
        except BaseException as exc:
            self._end_semantic_span(algorithm_span, error=exc)
            raise

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
        model_usage: object | None = None,
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
            model_usage=model_usage,
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
        self._record_middleware_spans()
        metadata = dict(result.metadata)
        metadata["middleware"] = self.middleware.metadata()
        return AgentResult(
            output=result.output,
            strategy_name=result.strategy_name,
            calls=result.calls,
            metadata=metadata,
            structured=result.structured,
        )

    async def execute_tool_call(self, call: ToolCall, *, provider: str, trace_context: SpanContext | None = None, iteration_count: int | None = None, tool_is_internal: bool = False) -> tuple[ToolCallContext, ToolResult]:
        # Resolves, authorizes, validates, executes, and records one tool call with optional timeout.
        tool_input = _safe_trace_value(dict(call.arguments))
        tool_span = self._tracer.start_span(
            "tool.call",
            parent=trace_context,
            tool_name=call.tool_name,
            tool_input=tool_input,
            arguments=tool_input,
            call_id=call.call_id,
            provider=provider,
            metadata=_safe_trace_mapping(call.metadata),
        )
        try:
            tool = self._get_tool(call)
            call = ActivityToolFormatter.prepare_call(tool, call)
            spec = tool.spec()
            self._check_permission(spec, call)
            self._validate_tool_call(tool, call)
            result = await self._execute_tool(tool, call, tool_is_internal=tool_is_internal)
            if spec.output_schema is not None and result.status.value == "success":
                _, error = self._schema_formatter.validate(result.output, spec.output_schema)
                if error:
                    result = ToolResult.error(
                        call.tool_name,
                        f"tool call error: output shape mismatch: {error}",
                        metadata={"error": "output_schema_violation", "detail": error},
                    )
            self._record_operation_usage(tool, call, result)
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
            error_code = str(exc.details.get("error", "execution_error"))
            error_type = exc.details.get("error_type", type(exc).__name__)
            result = ToolResult.error(
                call.tool_name,
                str(exc),
                metadata={"error": error_code, "error_type": error_type},
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
            self._build_tool_call_context(call, provider=provider, state=state, result=result, iteration_count=iteration_count, tool_is_internal=tool_is_internal),
            result,
        )

    def _record_operation_usage(self, tool: object, call: ToolCall, result: ToolResult) -> None:
        # Records one priced search/fetch operation per provider attempt a
        # PricedOperationTool call spent, so a retried or failed provider request stays
        # billable; swallows any hook error so a pricing bug can never break execution.
        # Unwrapping first keeps an activity-bound priced tool metered as itself.
        tool = ActivityToolFormatter.unwrap(tool) if isinstance(tool, BaseTool) else tool
        if not isinstance(tool, PricedOperationTool):
            return
        try:
            attempts = self._billable_attempts(tool, call, result)
            for _ in range(attempts):
                self.usage_tracker.record_operation(
                    tool.operation,
                    tool.provider,
                    mode=tool.mode_used(call, result),
                    units=tool.units_used(call, result),
                    reported_cost_usd=tool.reported_cost_usd(call, result),
                )
        except Exception:
            return

    def _billable_attempts(self, tool: PricedOperationTool, call: ToolCall, result: ToolResult) -> int:
        # Returns how many attempts to price, or zero when the call never reached the provider.
        if result.status.value != "success" and not tool.declares_usage(result):
            return 0
        if tool.units_used(call, result) < 1:
            return 0
        return max(0, tool.attempts_used(call, result))

    @staticmethod
    def _middleware_denied_tool(call: ToolCall, provider: str, decision: MiddlewareDecision, *, iteration_count: int | None = None) -> tuple[ToolCallContext, ToolResult]:
        # Converts a deny_tool middleware decision into a denied tool-call context.
        return AgentRuntime._denied_tool_result(call, provider, message=f"Tool denied by middleware: {decision.reason or 'middleware_denied'}", error="middleware_denied", reason=decision.reason, metadata=decision.metadata, iteration_count=iteration_count)

    @staticmethod
    def _denied_tool_result(call: ToolCall, provider: str, *, message: str, error: str, reason: str | None, metadata: Mapping[str, Any], iteration_count: int | None = None, tool_is_internal: bool = False) -> tuple[ToolCallContext, ToolResult]:
        # Builds a DENIED tool-call context and matching model-visible error result.
        result = ToolResult.error(call.tool_name, message, metadata={"error": error, "reason": reason, **dict(metadata)})
        context = AgentRuntime._build_tool_call_context(call, provider=provider, state=ToolCallState.DENIED, result=result, iteration_count=iteration_count, tool_is_internal=tool_is_internal)
        return context, result

    @staticmethod
    def _build_tool_call_context(call: ToolCall, *, provider: str, state: ToolCallState, result: ToolResult, iteration_count: int | None = None, tool_is_internal: bool = False) -> ToolCallContext:
        # Builds a ToolCallContext stamped with iteration index and internal marker when needed.
        metadata = dict(call.metadata)
        if tool_is_internal:
            metadata["internal"] = True
        return ToolCallContext(tool_name=call.tool_name, arguments=call.arguments, state=state, call_id=call.call_id, result=result, provider=provider, metadata=metadata, iteration_count=iteration_count, activity=call.activity)

    def _tool_is_internal(self, call: ToolCall) -> bool:
        """Return whether a call targets a runtime-only internal tool."""
        return self._tool_name_is_internal(call.tool_name)

    def _tool_name_is_internal(self, tool_name: str) -> bool:
        # Name-based internal check shared by _tool_is_internal and the contract counters.
        if tool_name == IS_DONE_TOOL_NAME:
            return True
        try:
            spec = self.tools._get(tool_name).spec()
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

    async def _execute_tool(self, tool: object, call: ToolCall, *, tool_is_internal: bool = False) -> ToolResult:
        # Executes the tool, optionally under tool_timeout_seconds, raising ToolExecutionError on failure.
        try:
            return await self._run_tool_execute(tool, call, tool_is_internal=tool_is_internal)
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(
                f"Tool execution failed: {exc}",
                details={"tool_name": call.tool_name, "error_type": type(exc).__name__},
            ) from exc

    async def _run_tool_execute(self, tool: object, call: ToolCall, *, tool_is_internal: bool) -> ToolResult:
        # Runs tool.execute, wrapping non-internal calls with ToolSettings.tool_timeout_seconds when set.
        settings = self.config.tool_settings
        timeout = None if tool_is_internal or settings is None else settings.tool_timeout_seconds
        if timeout is None:
            return await tool.execute(call)
        try:
            return await asyncio.wait_for(tool.execute(call), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise ToolExecutionError(
                f"Tool '{call.tool_name}' timed out after {timeout}s",
                details={"tool_name": call.tool_name, "error": "timeout", "error_type": "timeout"},
            ) from exc

    def _resolve_tool_schemas(self, provider: str) -> Sequence[dict[str, Any]]:
        """Return provider-native tool schemas when the toolkit is non-empty."""
        return self.tools.provider_schemas(provider) if len(self.tools) else ()

    @staticmethod
    def _extract_initial_messages(run_options: dict[str, Any]) -> list[dict[str, Any]]:
        """Pop and normalize the initial messages list from run options."""
        return [dict(item) for item in run_options.pop("messages", ())]

    def _llm_trace_inputs(self, handle: RunnerHandle, message: str, call_options: Mapping[str, Any], provider: str, iteration_count: int, model_call_count: int, metadata: Mapping[str, Any]) -> dict[str, Any]:
        # Build useful, bounded tracing inputs for the model-call child span.
        system = call_options.get("system")
        history_messages = tuple(_safe_trace_value(list(call_options.get("messages") or [])))
        tools = call_options.get("tools")
        safe_prompt = _trace_text(message)
        # Build a full chat-style messages list so LangSmith renders system prompt and user
        # prompt alongside the conversation context in the LLM call view.
        trace_messages: list[dict[str, Any]] = []
        if system is not None:
            trace_messages.append({"role": "system", "content": _trace_text(system)})
        trace_messages.extend(history_messages)
        trace_messages.append({"role": "user", "content": safe_prompt})
        input_messages = tuple(trace_messages)
        inputs: dict[str, Any] = {
            "agent_name": self.agent_name,
            "run_id": self.run_id,
            "provider": provider,
            "model": self._runner_model_name(handle.runner),
            "iteration": iteration_count,
            "model_call": model_call_count,
            "prompt": safe_prompt,
            "user_prompt": safe_prompt,
            "system": _trace_text(system) if system is not None else None,
            "messages": input_messages,
            "input_messages": input_messages,
            "metadata": _safe_trace_mapping(metadata),
        }
        if system is not None:
            inputs["system_prompt"] = _trace_text(system)
        if history_messages:
            inputs["history_messages"] = history_messages
        if tools:
            tool_list = list(tools)
            inputs["tools"] = _safe_trace_value(tool_list)
            inputs["tool_names"] = tuple(str(tool.get("name", "")) for tool in tool_list if isinstance(tool, Mapping) and tool.get("name"))
            inputs["tool_count"] = len(tool_list)
        inputs["context_window_summary"] = (
            f"system={len(system) if system else 0}chars, "
            f"messages={len(history_messages)}, "
            f"tools={len(list(tools)) if tools else 0}"
        )
        return inputs

    @staticmethod
    def _runner_model_name(runner: object) -> str | None:
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
        if model_name is not None:
            return str(model_name)
        return None

    def _build_iteration_call_options(self, run_options: dict[str, Any], context: BaseAgentContext, tool_schemas: Sequence[dict[str, Any]], messages: list[dict[str, Any]], provider: str = "", *, iteration_count: int = 0, tokens_used: int | None = None, tool_call_count: int = 0) -> dict[str, Any]:
        """Assemble per-iteration call options with system prompt, loop settings, primitives zone, tools, messages, and response format."""
        call_options = dict(run_options)
        loop_settings_block = self._render_loop_settings_block(
            iteration_count=iteration_count,
            tokens_used=tokens_used,
            tool_call_count=tool_call_count,
        )
        system = self._build_system_string(context, loop_settings_block=loop_settings_block)
        call_options.setdefault("system", system)
        if tool_schemas:
            call_options.setdefault("tools", tool_schemas)
        conversation_messages = self._build_conversation_messages(messages)
        if conversation_messages:
            call_options.setdefault("messages", conversation_messages)
        if self.output_schema is not None:
            call_options.setdefault("response_format", self._wire_schema())
        return call_options

    def _wire_schema(self) -> dict[str, Any]:
        # Resolves the declared schema once per runtime and folds unenforceable constraints into
        # descriptions. Providers wrap this; the runtime never builds a provider payload itself.
        if self._wire_schema_cache is None:
            self._wire_schema_cache = self._schema_formatter.annotate(self._schema_formatter.resolve_schema(self.output_schema))
        return self._wire_schema_cache

    def _validated_output(self, output: str) -> tuple[Any, str | None]:
        # Reuses the schema contract's own evaluation of this output so it is never parsed twice.
        for contract in self.output_contract.contracts:
            if isinstance(contract, SchemaConformance) and contract.schema is self.output_schema:
                return contract.evaluate({contract.key: output})
        return self._schema_formatter.validate(output, self.output_schema)

    def _build_conversation_messages(self, messages: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
        """Assemble placed context-window conversation messages around runtime messages."""
        # Preserves existing runtime messages while adding explicit conversation placements.
        if self.context_manager is None:
            return tuple(messages)
        top = self.context_manager.render_conversation_messages(ContextWindowPlacement.TOP_OF_CONVERSATION)
        end = self.context_manager.render_conversation_messages(ContextWindowPlacement.END_OF_CONVERSATION)
        return (*top, *tuple(messages), *end)

    def _build_system_string(self, context: BaseAgentContext, *, loop_settings_block: str = "") -> str:
        """Assemble the system string with fixed header, loop settings, primitives zone, and body in order."""
        # loop_settings_block is placed directly after the fixed system-prompt header so the agent
        # always sees its live loop budgets (current usage / configured limit) near the top of context.
        fixed = context.build_context_fixed()
        primitives_zone = self.context_manager.render_primitives_zone() if self.context_manager else ""
        body = context.build_context_body()
        parts = [p for p in (fixed, loop_settings_block, primitives_zone, body) if p]
        self._record_context_build_span(system_chars=len(fixed), primitive_chars=len(primitives_zone), body_chars=len(body))
        return "\n\n".join(parts)

    def _render_loop_settings_block(self, *, iteration_count: int, tokens_used: int | None, tool_call_count: int) -> str:
        """Render the agent-loop-settings context block as 'current usage / configured limit' lines.

        Only the budgets that are both numerically calculable and tracked by the runtime loop are
        injected (max_iterations, max_tokens, max_tool_calls). Settings without a live runtime
        measurement (max_retries, timeout_seconds, allowed_tools, etc.) are intentionally excluded.
        Returns an empty string when no relevant budget is configured.
        """
        lines: list[str] = []
        if self.config.max_iterations is not None:
            lines.append(f"- max_iterations: {iteration_count}/{self.config.max_iterations}")
        if self.config.max_tokens is not None:
            lines.append(f"- max_tokens: {tokens_used or 0}/{self.config.max_tokens}")
        if self.config.max_tool_calls is not None:
            lines.append(f"- max_tool_calls: {tool_call_count}/{self.config.max_tool_calls}")
        if not lines:
            return ""
        header = (
            "Below are your agent loop settings, shown as current usage / configured limit. "
            "Stay within these limits:"
        )
        return header + "\n" + "\n".join(lines)

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
            span = self._start_semantic_span("parser.structured_output", output_chars=len(output or ""))
            structured, validation_error = self._validated_output(output)
            if validation_error:
                self._end_semantic_span(span, error=ValueError(validation_error))
            else:
                self._end_semantic_span(span, output="validated")
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
        # Separate any activity annotation before policy so tool settings, middleware,
        # and identical-call limits all evaluate the tool's business arguments only.
        call = self.tools.prepare_call(call)
        tool_is_internal = self._tool_is_internal(call)
        settings_outcome = self._enforce_tool_settings(call, provider, messages, call_contexts, tool_is_internal, iteration_count=iteration_count, tokens_used=tokens_used)
        if settings_outcome is not None:
            return settings_outcome
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
        after_decision = MiddlewareDecision.continue_()
        while True:
            # Run the tool behind a retry-aware loop so middleware can silently
            # retry transient, idempotent failures. Only the final result escapes
            # this loop into call_contexts/messages, keeping intermediate failure
            # attempts out of the model-visible conversation history.
            if decision.action is MiddlewareAction.DENY_TOOL:
                context_record, result = self._middleware_denied_tool(call, provider, decision, iteration_count=iteration_count)
            else:
                context_record, result = await self.execute_tool_call(call, provider=provider, trace_context=trace_context, iteration_count=iteration_count, tool_is_internal=tool_is_internal)
            after_decision = await self.middleware.after_tool_call(
                self._middleware_context(
                    MiddlewareHook.AFTER_TOOL_CALL,
                    message=message,
                    context=context,
                    provider=provider,
                    iteration_count=iteration_count,
                    model_call_count=model_call_count,
                    tool_call_count=len(call_contexts) + 1,
                    tokens_used=tokens_used,
                    started_at=started_at,
                    metadata=self._tool_call_middleware_metadata(metadata, call),
                    run_state=run_state,
                    tool_call=call,
                    tool_result=result,
                    tool_is_internal=tool_is_internal,
                    model_response=model_response,
                )
            )
            if after_decision.action is not MiddlewareAction.RETRY:
                break
            if after_decision.sleep_seconds:
                await self.middleware.sleep(after_decision.sleep_seconds)
        call_contexts.append(context_record)
        if after_decision.action is MiddlewareAction.ABORT_RUN:
            return self._middleware_abort_result(
                after_decision,
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                contexts=call_contexts,
            )
        if call.tool_name != IS_DONE_TOOL_NAME:
            self._append_tool_result_message(messages, call, result, provider, after_decision)
        failure_stop = self._enforce_tool_settings_after_failure(context_record, tool_is_internal, call_contexts, iteration_count=iteration_count, tokens_used=tokens_used)
        if failure_stop is not None:
            return failure_stop
        return context_record, result

    def _enforce_tool_settings(self, call: ToolCall, provider: str, messages: list[dict[str, Any]], call_contexts: list[ToolCallContext], tool_is_internal: bool, *, iteration_count: int, tokens_used: int | None) -> tuple[ToolCallContext, ToolResult] | AgentResult | None:
        # Applies ToolSettings before local execution: hard budgets first, then deny-class rules.
        settings = self.config.tool_settings
        if settings is None or tool_is_internal:
            return None
        budget_stop = self._tool_settings_budget_stop(settings, call_contexts, iteration_count=iteration_count, tokens_used=tokens_used)
        if budget_stop is not None:
            return budget_stop
        hard_budget = settings.budget_stop(tool_name=call.tool_name, arguments=dict(call.arguments), call_contexts=call_contexts, iteration_count=iteration_count)
        if hard_budget is not None:
            reason, meta = hard_budget
            return self._tool_settings_hard_budget_stop(reason, meta, iteration_count=iteration_count, tokens_used=tokens_used, contexts=call_contexts)
        denial = settings.denial(call.tool_name, self._executed_counts(call_contexts))
        if denial is None:
            return None
        return self._apply_tool_denial(settings, call, provider, messages, call_contexts, denial, iteration_count=iteration_count, tokens_used=tokens_used)

    def _tool_settings_budget_stop(self, settings: ToolSettings, call_contexts: list[ToolCallContext], *, iteration_count: int, tokens_used: int | None) -> AgentResult | None:
        # Stops the run before executing a call that would exceed the total tool-call budget mid-iteration.
        if settings.max_calls is None or len(call_contexts) < settings.max_calls:
            return None
        return self._stopped_result("Agent runtime stopped after reaching max_tool_calls.", stop_reason=AgentStopReason.MAX_TOOL_CALLS, iteration_count=iteration_count, tokens_used=tokens_used, contexts=call_contexts)

    def _tool_settings_hard_budget_stop(self, reason: str, meta: Mapping[str, Any], *, iteration_count: int, tokens_used: int | None, contexts: Sequence[ToolCallContext]) -> AgentResult:
        # Maps a ToolSettings hard-budget reason string to AgentStopReason and stops the run with budget metadata.
        stop_reason = self._agent_stop_reason_for_tool_budget(reason)
        result = self._stopped_result(f"Agent runtime stopped by tool settings budget: {reason}", stop_reason=stop_reason, iteration_count=iteration_count, tokens_used=tokens_used, contexts=contexts)
        return AgentResult(output=result.output, strategy_name=result.strategy_name, structured=result.structured, metadata={**dict(result.metadata), "tool_settings_budget": reason, **dict(meta)})

    @staticmethod
    def _agent_stop_reason_for_tool_budget(reason: str) -> AgentStopReason:
        # Converts pure ToolSettings budget reason keys into AgentStopReason enum values.
        mapping = {
            "max_calls_per_iteration": AgentStopReason.MAX_CALLS_PER_ITERATION,
            "max_identical_calls": AgentStopReason.MAX_IDENTICAL_CALLS,
            "max_consecutive_failures": AgentStopReason.MAX_CONSECUTIVE_FAILURES,
            "max_error_calls": AgentStopReason.MAX_ERROR_CALLS,
            "sliding_window_max_calls": AgentStopReason.SLIDING_WINDOW_MAX_CALLS,
        }
        return mapping.get(reason, AgentStopReason.TOOL_SETTINGS_DENIED)

    def _enforce_tool_settings_after_failure(self, context_record: ToolCallContext, tool_is_internal: bool, call_contexts: Sequence[ToolCallContext], *, iteration_count: int, tokens_used: int | None) -> AgentResult | None:
        # Hard-stops after a failed non-internal tool when consecutive or total error budgets are hit.
        settings = self.config.tool_settings
        if settings is None or tool_is_internal or context_record.state is not ToolCallState.FAILED:
            return None
        failure_stop = settings.failure_budget_stop(call_contexts)
        if failure_stop is None:
            return None
        reason, meta = failure_stop
        return self._tool_settings_hard_budget_stop(reason, meta, iteration_count=iteration_count, tokens_used=tokens_used, contexts=call_contexts)

    def _apply_tool_denial(self, settings: ToolSettings, call: ToolCall, provider: str, messages: list[dict[str, Any]], call_contexts: list[ToolCallContext], denial: tuple[str, dict], *, iteration_count: int, tokens_used: int | None) -> tuple[ToolCallContext, ToolResult] | AgentResult:
        # Aborts the run or records an in-context denial according to the on_deny policy.
        reason, meta = denial
        if settings.aborts_on_deny:
            return self._stopped_result(f"Agent runtime stopped by tool settings: {reason}", stop_reason=AgentStopReason.TOOL_SETTINGS_DENIED, iteration_count=iteration_count, tokens_used=tokens_used, contexts=call_contexts)
        context_record, result = self._denied_tool_result(call, provider, message=f"Tool denied by tool settings: {reason}", error=reason, reason=reason, metadata=meta, iteration_count=iteration_count)
        call_contexts.append(context_record)
        self._append_tool_result_message(messages, call, result, provider, MiddlewareDecision.continue_(), truncate=False)
        return context_record, result

    @staticmethod
    def _executed_counts(call_contexts: Sequence[ToolCallContext]) -> dict[str, int]:
        # Counts prior executed (non-denied) tool calls per tool name for per-tool budgets.
        counts: dict[str, int] = {}
        for ctx in call_contexts:
            if ctx.state is ToolCallState.DENIED:
                continue
            counts[ctx.tool_name] = counts.get(ctx.tool_name, 0) + 1
        return counts

    def _append_tool_result_message(
        self,
        messages: list[dict[str, Any]],
        call: ToolCall,
        result: ToolResult,
        provider: str,
        decision: MiddlewareDecision,
        *,
        truncate: bool = True,
    ) -> None:
        visible_result = self._model_visible_tool_result(call, result, decision, truncate=truncate)
        # Provider-specific result formatting remains the single place that
        # knows how Anthropic, Gemini, OpenAI Responses, and OpenAI-compatible
        # chat messages represent tool failures.
        formatted = ToolsFormatter.format_tool_result(call, visible_result, provider)
        messages.append(dict(formatted))

    def _model_visible_tool_result(
        self,
        call: ToolCall,
        result: ToolResult,
        decision: MiddlewareDecision,
        *,
        truncate: bool = True,
    ) -> ToolResult:
        # Primitive binding is applied before any middleware-visible transform so
        # successful tool outputs can still be stored as primitives. Error results
        # bypass primitive binding and keep their full details for formatter output.
        primitive_result = self._apply_primitive_binding(call, result)
        if primitive_result is not result:
            return primitive_result
        visible = result if decision.transform is None else (decision.transform.model_visible_tool_result or result)
        if not truncate:
            return visible
        return self._truncate_for_tool_settings(call, visible)

    def _truncate_for_tool_settings(self, call: ToolCall, result: ToolResult) -> ToolResult:
        # Caps executed, non-internal tool output to ToolSettings.result_max_chars, leaving raw ToolResult intact.
        settings = self.config.tool_settings
        if settings is None or self._tool_is_internal(call):
            return result
        return settings.truncate(result)

    def _tool_call_middleware_metadata(self, metadata: Mapping[str, Any], call: ToolCall) -> dict[str, Any]:
        call_metadata = dict(metadata)
        call_metadata["tool_permission"] = self._tool_permission_for_call(call)
        return call_metadata

    def _tool_permission_for_call(self, call: ToolCall) -> str | None:
        try:
            spec = self.tools._get(call.tool_name).spec()
        except Exception:
            return None
        permission = getattr(spec, "permission", None)
        if permission is None:
            return None
        return str(getattr(permission, "value", permission))

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
        if self.config.max_tool_calls is not None and len(contexts) >= self.config.max_tool_calls:
            return self._stopped_result(
                "Agent runtime stopped after reaching max_tool_calls.",
                stop_reason=AgentStopReason.MAX_TOOL_CALLS,
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
            "usage_rollup": self.usage_tracker.rollup(),
        }

    def _contract_counters(self, *, iteration_count: int, model_call_count: int, call_contexts: Sequence[ToolCallContext], tokens_used: int | None, started_at: float, final_output: str | None = None, compaction_count: int = 0) -> dict[str, Any]:
        # Packages the live runtime counters into the dict output contracts read by key.
        # Internal tools (e.g. isDone) are excluded so effort floors count only real work.
        final_text = final_output or ""
        non_internal = self._non_internal_tool_contexts(call_contexts)
        return {
            "iteration_count": iteration_count,
            "model_call_count": model_call_count,
            "tool_call_count": len(non_internal),
            "successful_tool_call_count": self._successful_tool_call_count(non_internal),
            "distinct_tool_count": self._distinct_tool_count(non_internal),
            "tool_calls_by_name": self._tool_calls_by_name(non_internal),
            "tokens_used": tokens_used or 0,
            "elapsed_seconds": self.middleware.clock() - started_at,
            "final_output_chars": len(final_text),
            "final_output_tokens": self._approx_output_tokens(final_text),
            "cost_spent_usd": self._cost_spent_usd(tokens_used),
            "compaction_count": compaction_count,
        }

    def _non_internal_tool_contexts(self, call_contexts: Sequence[ToolCallContext]) -> list[ToolCallContext]:
        # Filters out internal tools so effort floors count only developer-facing work.
        return [context for context in call_contexts if not self._tool_name_is_internal(context.tool_name)]

    def _successful_tool_call_count(self, call_contexts: Sequence[ToolCallContext]) -> int:
        # Counts tool contexts that finished with SUCCEEDED (excludes failures and denials).
        return sum(1 for context in call_contexts if context.state is ToolCallState.SUCCEEDED)

    def _distinct_tool_count(self, call_contexts: Sequence[ToolCallContext]) -> int:
        # Counts unique tool names across the provided (already non-internal) contexts.
        return len({context.tool_name for context in call_contexts})

    def _tool_calls_by_name(self, call_contexts: Sequence[ToolCallContext]) -> dict[str, int]:
        # Builds a histogram of non-internal tool call counts keyed by tool name.
        counts: dict[str, int] = {}
        for context in call_contexts:
            counts[context.tool_name] = counts.get(context.tool_name, 0) + 1
        return counts

    @staticmethod
    def _approx_output_tokens(text: str) -> int:
        # Estimates tokens deterministically as ceil(chars/4), matching compaction heuristics.
        return max(1, math.ceil(len(text) / 4)) if text else 0

    def _cost_spent_usd(self, tokens_used: int | None) -> float:
        # Returns estimated USD spend from CostBudgetMiddleware when attached, else 0.0.
        del tokens_used
        from vidbyte.middleware.builtins.cost_budget import CostBudgetMiddleware

        for middleware in self.middleware.middleware:
            if isinstance(middleware, CostBudgetMiddleware):
                return float(middleware.estimated_spend_usd)
        return 0.0

    def _compaction_event_delta(self, decision: MiddlewareDecision) -> int:
        # Returns 1 when a history compaction transform actually mutated provider messages.
        transform = decision.transform
        if transform is None or transform.provider_messages is None:
            return 0
        meta = dict(transform.metadata or {})
        if "compaction" not in meta:
            return 0
        before = meta.get("before_count")
        after = meta.get("after_count")
        if before is not None and after is not None:
            return 1 if int(before) != int(after) else 0
        return 1

    def _publish_contract_evaluations(self, run_state: dict[type, Any], counters: Mapping[str, Any]) -> None:
        # Records each contract's evaluation into run_state so _with_run_state_metadata lifts it into the result.
        run_state.setdefault("__result_metadata__", {})["contract_evaluations"] = self.output_contract.report(counters)

    @staticmethod
    def _assistant_message(output: str) -> dict[str, Any]:
        return {"role": "assistant", "content": output}

    @staticmethod
    def _add_token_usage(current: int | None, delta: int | None) -> int | None:
        if delta is None:
            return current
        return (current or 0) + delta

    def _start_semantic_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext | None:
        # Opens optional semantic-only spans when the active tracer is a TraceController.
        if not _is_semantic_tracer(self._tracer):
            return None
        return self._tracer.start_span(name, parent=parent, **attributes)

    def _end_semantic_span(self, context: SpanContext | None, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes optional semantic-only spans when one was opened.
        if context is None:
            return
        self._tracer.end_span(context, output=output, error=error)

    def _record_parser_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> None:
        # Records a short parser span without affecting parser behavior.
        span = self._start_semantic_span(name, parent=parent, **attributes)
        self._end_semantic_span(span, output="ok")

    def _record_context_build_span(self, **attributes: Any) -> None:
        # Records a context-window build summary when semantic tracing is active.
        span = self._start_semantic_span("context.window.build", **attributes)
        self._end_semantic_span(span, output="built")

    def _record_middleware_spans(self) -> None:
        # Emits spans for middleware decisions captured by the middleware pipeline.
        for event in self.middleware.events:
            span = self._start_semantic_span(
                "middleware.decision",
                middleware_name=event.middleware_name,
                hook=event.hook.value,
                action=event.action.value,
                reason=event.reason,
                metadata=dict(event.metadata),
            )
            self._end_semantic_span(span, output=event.action.value)


def _trace_text(value: object, *, max_chars: int = 12000) -> str:
    # Keep trace payloads useful without letting very large prompts dominate requests.
    text = str(value)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...[truncated]"


def _safe_trace_mapping(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    # Removes env/credential-like fields before sending user metadata to tracing backends.
    safe: dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        key_text = str(key)
        upper = key_text.upper()
        if upper.startswith("LANGSMITH_") or any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")):
            continue
        safe[key_text] = _safe_trace_value(value)
    return safe


def _safe_trace_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _safe_trace_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_safe_trace_value(item) for item in value)
    if isinstance(value, str):
        return _trace_text(value)
    return value


def _is_semantic_tracer(tracer: TracerBase) -> bool:
    # Detects TraceController-like tracers without importing vidbyte.trace during agent initialization.
    return all(hasattr(tracer, attr) for attr in ("inner", "profile", "translator"))


__all__ = ["AgentRuntime"]

