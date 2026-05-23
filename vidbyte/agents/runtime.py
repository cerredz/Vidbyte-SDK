"""Context Protocol Header

Description:
    Defines the internal direct execution runtime for Vidbyte agents.
Purpose:
    Keeps agent loop execution, context-window construction, tool execution,
    permission checks, and minimal budget tracking out of BaseAgent.
Architecture:
    - AgentRuntime: Builds BaseAgentContext and runs direct model/tool loops.
Relations:
    Used by vidbyte.agents.base. Depends on shared context, tool, security, and
    strategy dataclasses without owning modality routing or runner construction.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig, AgentStopReason
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.strategies.types import BaseAgentContext, StrategyContext, StrategyResult
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
    ) -> None:
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.permission_policy = permission_policy
        self.config = config or AgentRuntimeConfig()

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
    ) -> BaseAgentContext:
        """Build the context window passed into direct runners and strategies."""
        merged_history = tuple(history) + tuple(agent_history)
        metadata = dict(base_context.metadata if base_context else {})
        metadata.update(dict(agent_metadata))
        metadata.update(dict(input_metadata or {}))
        if modality is not None:
            metadata["modality"] = modality.value

        strategy_metadata = dict(base_context.strategy_metadata if base_context else {})
        strategy_metadata.update({"current_agent": self.agent_name, "current_message": message})
        if modality is not None:
            strategy_metadata["modality"] = modality.value

        tool_calls = (
            tuple(base_context.tool_calls) + tuple(existing_tool_calls)
            if base_context
            else tuple(existing_tool_calls)
        )

        return BaseAgentContext(
            system_prompt=base_context.system_prompt
            if base_context and base_context.system_prompt
            else self.system_prompt,
            agent_name=self.agent_name,
            role=base_context.role if base_context else None,
            history=merged_history,
            file_paths=tuple(base_context.file_paths) if base_context else (),
            strategy_metadata=strategy_metadata,
            tool_calls=tool_calls,
            responses=tuple(base_context.responses) if base_context else (),
            budget=base_context.budget if base_context else None,
            artifacts=tuple(base_context.artifacts) if base_context else (),
            memory=base_context.memory if base_context else None,
            permissions=base_context.permissions if base_context else None,
            metadata=metadata,
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
        options: Mapping[str, Any] | None = None,
    ) -> StrategyResult:
        """Run the direct model/tool loop until final response or budget stop."""
        run_options = dict(options or {})
        tool_schemas = self.tools.provider_schemas(provider) if len(self.tools) else ()
        messages: list[dict[str, Any]] = [dict(item) for item in run_options.pop("messages", ())]
        call_contexts: list[ToolCallContext] = []
        iteration_count = 0
        estimated_tokens = self._estimate_tokens(message, context.build_context(), messages)

        stop_result = self._budget_stop(
            iteration_count=iteration_count,
            estimated_tokens=estimated_tokens,
            contexts=call_contexts,
        )
        if stop_result is not None:
            return stop_result

        while True:
            call_options = dict(run_options)
            call_options.setdefault("system", context.system_prompt)
            if tool_schemas:
                call_options.setdefault("tools", tool_schemas)
            if messages:
                call_options.setdefault("messages", tuple(messages))

            raw_result = await invoke_runner(runner, message, **call_options)
            iteration_count += 1
            runner_metadata = dict(runner_output_metadata(raw_result))
            estimated_tokens += self._estimate_response_tokens(raw_result, runner_metadata)

            tool_calls = ToolsFormatter.parse_tool_calls(raw_result, provider)
            if not tool_calls:
                return StrategyResult(
                    output=runner_output_text(raw_result),
                    strategy_name="direct_runner",
                    metadata={
                        **self._runtime_metadata(
                            contexts=call_contexts,
                            iteration_count=iteration_count,
                            estimated_tokens=estimated_tokens,
                            stop_reason=AgentStopReason.FINAL_RESPONSE,
                        ),
                        **runner_metadata,
                    },
                )

            for call in tool_calls:
                context_record, result = await self.execute_tool_call(call, provider=provider)
                call_contexts.append(context_record)
                messages.append(dict(ToolsFormatter.format_tool_result(call, result, provider)))
                estimated_tokens += self._estimate_tokens(result.output)

            stop_result = self._budget_stop(
                iteration_count=iteration_count,
                estimated_tokens=estimated_tokens,
                contexts=call_contexts,
            )
            if stop_result is not None:
                return stop_result

    async def execute_tool_call(
        self,
        call: ToolCall,
        *,
        provider: str,
    ) -> tuple[ToolCallContext, ToolResult]:
        """Resolve, authorize, validate, execute, and record one tool call."""
        try:
            tool = self.tools._get(call.tool_name)
        except Exception as exc:
            result = ToolResult.error(call.tool_name, str(exc), metadata={"error": "unknown_tool"})
            return (
                ToolCallContext(
                    tool_name=call.tool_name,
                    arguments=call.arguments,
                    state=ToolCallState.FAILED,
                    call_id=call.call_id,
                    result=result,
                    provider=provider,
                    metadata=dict(call.metadata),
                ),
                result,
            )

        spec = tool.spec()
        decision = self.permission_policy.check(spec, call)
        if decision is PermissionDecision.DENY:
            result = ToolResult.error(
                spec.name,
                f"Permission denied for tool '{spec.name}' requiring {spec.permission.value}",
                metadata={"error": "permission_denied", "permission": spec.permission.value},
            )
            return (
                ToolCallContext(
                    tool_name=spec.name,
                    arguments=call.arguments,
                    state=ToolCallState.DENIED,
                    call_id=call.call_id,
                    result=result,
                    provider=provider,
                    metadata=dict(call.metadata),
                ),
                result,
            )

        validation_error = tool.validate_call(call)
        if validation_error:
            result = ToolResult.error(spec.name, validation_error, metadata={"error": "validation_error"})
            return (
                ToolCallContext(
                    tool_name=spec.name,
                    arguments=call.arguments,
                    state=ToolCallState.FAILED,
                    call_id=call.call_id,
                    result=result,
                    provider=provider,
                    metadata=dict(call.metadata),
                ),
                result,
            )

        try:
            result = await tool.execute(call)
            state = ToolCallState.SUCCEEDED if result.status.value == "success" else ToolCallState.FAILED
        except Exception as exc:
            result = ToolResult.error(
                spec.name,
                f"Tool execution failed: {exc}",
                metadata={"error": "execution_error", "error_type": type(exc).__name__},
            )
            state = ToolCallState.FAILED

        return (
            ToolCallContext(
                tool_name=spec.name,
                arguments=call.arguments,
                state=state,
                call_id=call.call_id,
                result=result,
                provider=provider,
                metadata=dict(call.metadata),
            ),
            result,
        )

    def _budget_stop(
        self,
        *,
        iteration_count: int,
        estimated_tokens: int,
        contexts: Sequence[ToolCallContext],
    ) -> StrategyResult | None:
        if self.config.max_iterations is not None and iteration_count >= self.config.max_iterations:
            return self._stopped_result(
                "Agent runtime stopped after reaching max_iterations.",
                stop_reason=AgentStopReason.MAX_ITERATIONS,
                iteration_count=iteration_count,
                estimated_tokens=estimated_tokens,
                contexts=contexts,
            )
        if self.config.max_tokens is not None and estimated_tokens >= self.config.max_tokens:
            return self._stopped_result(
                "Agent runtime stopped after reaching max_tokens.",
                stop_reason=AgentStopReason.MAX_TOKENS,
                iteration_count=iteration_count,
                estimated_tokens=estimated_tokens,
                contexts=contexts,
            )
        return None

    def _stopped_result(
        self,
        output: str,
        *,
        stop_reason: AgentStopReason,
        iteration_count: int,
        estimated_tokens: int,
        contexts: Sequence[ToolCallContext],
    ) -> StrategyResult:
        return StrategyResult(
            output=output,
            strategy_name="direct_runner",
            metadata=self._runtime_metadata(
                contexts=contexts,
                iteration_count=iteration_count,
                estimated_tokens=estimated_tokens,
                stop_reason=stop_reason,
            ),
        )

    def _runtime_metadata(
        self,
        *,
        contexts: Sequence[ToolCallContext],
        iteration_count: int,
        estimated_tokens: int,
        stop_reason: AgentStopReason,
    ) -> dict[str, Any]:
        return {
            "stop_reason": stop_reason.value,
            "iteration_count": iteration_count,
            "estimated_tokens": estimated_tokens,
            "tool_call_count": len(contexts),
            "tool_call_states": tuple(context.state.value for context in contexts),
            "tool_calls": tuple(contexts),
        }

    def _estimate_response_tokens(self, result: object, metadata: Mapping[str, Any]) -> int:
        usage_tokens = self._usage_total_tokens(metadata)
        if usage_tokens is not None:
            return usage_tokens
        raw_payload = getattr(result, "raw", None)
        return self._estimate_tokens(self._safe_runner_text(result), raw_payload)

    @staticmethod
    def _usage_total_tokens(metadata: Mapping[str, Any]) -> int | None:
        usage = metadata.get("usage")
        if isinstance(usage, Mapping):
            total = usage.get("total_tokens") or usage.get("input_tokens")
            if isinstance(total, int):
                return total
        total_tokens = metadata.get("total_tokens")
        return total_tokens if isinstance(total_tokens, int) else None

    @staticmethod
    def _estimate_tokens(*items: object) -> int:
        total_chars = 0
        for item in items:
            if item is None:
                continue
            if isinstance(item, str):
                total_chars += len(item)
            else:
                total_chars += len(str(item))
        if total_chars <= 0:
            return 0
        return max(1, (total_chars + 3) // 4)

    @staticmethod
    def _safe_runner_text(result: object) -> str:
        text = getattr(result, "text", None)
        if text is not None:
            return str(text)
        output = getattr(result, "output", None)
        if output is not None:
            return str(output)
        return str(result)


__all__ = ["AgentRuntime"]
