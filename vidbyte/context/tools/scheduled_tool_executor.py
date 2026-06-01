"""Context Protocol Header

Description:
    Canonical executor for context-window algorithm scheduled tool calls.
Purpose:
    Provides the single authoritative path for executing algorithm-scheduled
    tool calls with middleware, permissions, validation, and tracing — without
    emitting provider-native tool-result messages.
Architecture:
    - ScheduledToolExecutor: Runs a supplied BaseTool through the full middleware
      and permission pipeline and returns a ToolCallContext/ToolResult pair or
      an AgentResult when middleware aborts the run.
Relations:
    Used by context-window algorithm adapters (e.g. AdversarialReflectionRuntimeAlgorithm)
    via AgentRuntime.execute_scheduled_tool_call.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.middleware import MiddlewareAction, MiddlewareHook
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import PermissionDeniedError, ToolExecutionError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools.types import ToolCall, ToolCallContext, ToolCallState, ToolResult

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


class ScheduledToolExecutor:
    """Executes algorithm-scheduled tools through middleware, permissions, and tracing."""

    def __init__(self, runtime: AgentRuntime) -> None:
        # Bind the parent runtime to reuse its middleware, tracer, and permission helpers.
        self._runtime = runtime

    async def execute(
        self,
        tool: object,
        call: ToolCall,
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
        trace_context: SpanContext | None = None,
    ) -> tuple[ToolCallContext, ToolResult] | AgentResult:
        # Run before_tool_call middleware; abort or deny the tool call when requested.
        tool_is_internal = self._is_tool_internal(tool)
        before_decision = await self._runtime.middleware.before_tool_call(
            self._runtime._middleware_context(
                MiddlewareHook.BEFORE_TOOL_CALL,
                message=message,
                context=context,
                provider=provider,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                tool_call_count=0,
                tokens_used=tokens_used,
                started_at=started_at,
                metadata=metadata,
                tool_call=call,
                tool_is_internal=tool_is_internal,
                model_response=model_response,
            )
        )
        if before_decision.action is MiddlewareAction.ABORT_RUN:
            return self._runtime._middleware_abort_result(
                before_decision, iteration_count=iteration_count, tokens_used=tokens_used, contexts=()
            )
        if before_decision.action is MiddlewareAction.DENY_TOOL:
            context_record, result = self._runtime._middleware_denied_tool(call, provider, before_decision)
        else:
            context_record, result = await self._run_tool(tool, call, provider=provider, trace_context=trace_context)
        return await self._apply_after_middleware(
            context_record=context_record,
            result=result,
            call=call,
            tool_is_internal=tool_is_internal,
            message=message,
            context=context,
            provider=provider,
            iteration_count=iteration_count,
            model_call_count=model_call_count,
            tokens_used=tokens_used,
            started_at=started_at,
            metadata=metadata,
            model_response=model_response,
        )

    async def _run_tool(
        self,
        tool: object,
        call: ToolCall,
        *,
        provider: str,
        trace_context: SpanContext | None = None,
    ) -> tuple[ToolCallContext, ToolResult]:
        # Execute the tool with tracing, permission checks, and validation; capture any errors as ToolResult.
        tool_span = self._runtime._tracer.start_span("tool.call", parent=trace_context, tool_name=call.tool_name)
        try:
            spec = tool.spec()
            self._runtime._check_permission(spec, call)
            self._runtime._validate_tool_call(tool, call)
            result = await self._runtime._execute_tool(tool, call)
            state = ToolCallState.SUCCEEDED if result.status.value == "success" else ToolCallState.FAILED
            self._runtime._tracer.end_span(tool_span, output=result.output)
        except PermissionDeniedError as exc:
            permission = exc.details.get("permission", "")
            result = ToolResult.error(call.tool_name, str(exc), metadata={"error": "permission_denied", "permission": permission})
            state = ToolCallState.DENIED
            self._runtime._tracer.end_span(tool_span, error=exc)
        except ToolExecutionError as exc:
            error_type = exc.details.get("error_type", type(exc).__name__)
            result = ToolResult.error(call.tool_name, str(exc), metadata={"error": "execution_error", "error_type": error_type})
            state = ToolCallState.FAILED
            self._runtime._tracer.end_span(tool_span, error=exc)
        except Exception as exc:
            result = ToolResult.error(call.tool_name, f"Tool execution failed: {exc}", metadata={"error": "execution_error", "error_type": type(exc).__name__})
            state = ToolCallState.FAILED
            self._runtime._tracer.end_span(tool_span, error=exc)
        return (
            ToolCallContext(tool_name=call.tool_name, arguments=call.arguments, state=state, call_id=call.call_id, result=result, provider=provider, metadata=dict(call.metadata)),
            result,
        )

    async def _apply_after_middleware(
        self,
        *,
        context_record: ToolCallContext,
        result: ToolResult,
        call: ToolCall,
        tool_is_internal: bool,
        message: str,
        context: BaseAgentContext,
        provider: str,
        iteration_count: int,
        model_call_count: int,
        tokens_used: int | None,
        started_at: float,
        metadata: Mapping[str, Any],
        model_response: object | None,
    ) -> tuple[ToolCallContext, ToolResult] | AgentResult:
        # Run after_tool_call middleware and abort the run if requested.
        after_decision = await self._runtime.middleware.after_tool_call(
            self._runtime._middleware_context(
                MiddlewareHook.AFTER_TOOL_CALL,
                message=message,
                context=context,
                provider=provider,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                tool_call_count=1,
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
            return self._runtime._middleware_abort_result(
                after_decision, iteration_count=iteration_count, tokens_used=tokens_used, contexts=(context_record,)
            )
        return context_record, result

    @staticmethod
    def _is_tool_internal(tool: object) -> bool:
        # Read the internal metadata flag from the tool spec without raising on missing spec fields.
        spec = tool.spec()
        metadata = getattr(spec, "metadata", {})
        return bool(isinstance(metadata, Mapping) and metadata.get("internal"))


__all__ = [
    "ScheduledToolExecutor",
]
