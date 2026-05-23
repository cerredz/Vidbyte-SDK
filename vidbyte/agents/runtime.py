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

from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig, AgentStopReason
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import PermissionDeniedError, ToolExecutionError, ToolRegistryError
from vidbyte.lib.token_usage import token_usage_from_response
from vidbyte.lib.tools import ToolsFormatter
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
    ) -> None:
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = with_internal_agent_tools(tools)
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
        """Build the minimal context window passed into direct runners and strategies."""
        del message, agent_metadata, existing_tool_calls, input_metadata, modality
        system_prompt = base_context.system_prompt if base_context and base_context.system_prompt else self.system_prompt
        return BaseAgentContext(
            system_prompt=append_agentic_loop_prompt(system_prompt),
            history=tuple(history) + tuple(agent_history),
            file_paths=tuple(base_context.file_paths) if base_context else (),
            tools=self.tools.specs(),
            budget=base_context.budget if base_context else None,
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
        """Run the direct model/tool loop until isDone or a budget stop."""
        run_options = dict(options or {})
        tool_schemas = self._resolve_tool_schemas(provider)
        messages = self._extract_initial_messages(run_options)
        call_contexts: list[ToolCallContext] = []
        iteration_count = 0
        tokens_used: int | None = None

        while True:
            stop_result = self._budget_stop(
                iteration_count=iteration_count,
                tokens_used=tokens_used,
                contexts=call_contexts,
            )
            if stop_result is not None:
                return stop_result

            call_options = self._build_iteration_call_options(run_options, context, tool_schemas, messages)
            raw_result = await invoke_runner(runner, message, **call_options)
            iteration_count += 1
            runner_metadata = dict(runner_output_metadata(raw_result))
            tokens_used = self._add_token_usage(tokens_used, token_usage_from_response(raw_result, runner_metadata))

            tool_calls = ToolsFormatter.parse_tool_calls(raw_result, provider)
            if not tool_calls:
                messages.append(self._assistant_message(runner_output_text(raw_result)))
                continue

            for call in tool_calls:
                _, result = await self._process_tool_call(call, provider, messages, call_contexts)
                if call.tool_name == IS_DONE_TOOL_NAME:
                    return self._final_result(
                        output=result.output,
                        runner_metadata=runner_metadata,
                        contexts=call_contexts,
                        iteration_count=iteration_count,
                        tokens_used=tokens_used,
                        stop_reason=AgentStopReason.IS_DONE,
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
    ) -> tuple[ToolCallContext, ToolResult]:
        """Execute one tool call, record its context, and append it to messages."""
        context_record, result = await self.execute_tool_call(call, provider=provider)
        call_contexts.append(context_record)
        if call.tool_name != IS_DONE_TOOL_NAME:
            messages.append(dict(ToolsFormatter.format_tool_result(call, result, provider)))
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


__all__ = ["AgentRuntime"]
