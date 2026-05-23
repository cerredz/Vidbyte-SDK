"""Context Protocol Header

Description:
    Defines the baseline agent implementation (BaseAgent) and configured runner wrappers.
Purpose:
    Combines prompting, tool registration, runtime state tracking, and strategy pipelines
    into a unified developer-facing executable actor (the agent).
Architecture:
    - BaseAgent: Primary agent class inheriting MCP attachment capabilities.
    - ConfiguredAgentRunner: Simple payload carrier for backend runner parameters.
Relations:
    Inherits from McpAttachableMixin. Used by registries, harnesses, and strategy orchestration blocks.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidbyte.tools.agent_tool import AgentTool

from vidbyte.agents.mixins import McpAttachableMixin
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage
from vidbyte.lib.agents import ModalityDetector
from vidbyte.lib.dataclasses.agents import AgentRunnerConfig
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import BaseAgentContext, StrategyContext, StrategyResult
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionDecision, PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolCallContext, ToolCallState, ToolResult, ToolSpec


class ConfiguredAgentRunner:
    """Runner placeholder created from primitive agent configuration."""

    def __init__(self, config: AgentRunnerConfig) -> None:
        self.config = config


class BaseAgent(McpAttachableMixin):
    """Reusable actor combining a system prompt, optional strategy, runner, and tools."""

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        strategy: BaseStrategy | None = None,
        runner: object | None = None,
        runners: Mapping[ModelModality | str, object] | None = None,
        tools: Sequence[object] | Tools = (),
        permission_policy: PermissionPolicy | None = None,
        max_tool_rounds: int = 3,
        api_key: str | None = None,
        provider: ModelProvider | str | None = None,
        model_name: str | None = None,
        modality: ModelModality | str = ModelModality.AUTO,
        temperature: float | None = None,
        run_id: str | None = None,
        runner_options: dict[str, Any] | None = None,
        description: str = "",
        capabilities: Sequence[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not name:
            raise AgentExecutionError("Agent name cannot be empty.")
        if not system_prompt:
            raise AgentExecutionError("Agent system_prompt is required.")
        self.runner_config = AgentRunnerConfig(
            api_key=api_key,
            provider=str(provider.value if isinstance(provider, ModelProvider) else provider) if provider is not None else None,
            model_name=model_name,
            modality=modality,
            temperature=temperature,
            run_id=run_id,
            options=dict(runner_options or {}),
        )
        self.name = name
        self.strategy = strategy
        self.runner = runner if runner is not None else self._create_runner()
        self.runners = {
            ModalityDetector.coerce(runner_modality): runner_item
            for runner_modality, runner_item in dict(runners or {}).items()
        }
        self.modality = ModalityDetector.coerce(modality)
        self._agent_tool_items = tools.all() if isinstance(tools, Tools) else tuple(tools)
        self.tools = tools if isinstance(tools, Tools) else self._catalog_from_agent_tools(self._agent_tool_items)
        self.permission_policy = permission_policy or PermissionPolicy()
        self.max_tool_rounds = max(0, max_tool_rounds)
        self.system_prompt = system_prompt
        self.description = description or "General purpose agent."
        self.capabilities = tuple(capabilities)
        self.metadata = dict(metadata or {})
        self.history: list[AgentMessage] = []
        self._tool_call_contexts: list[ToolCallContext] = []

        # MCP Attachable State
        self._mcp_handles = []
        self._pending_mcp_configs = []

    @classmethod
    def from_run_id(
        cls,
        run_id: str,
        *,
        name: str,
        system_prompt: str,
        strategy: BaseStrategy | None = None,
        **kwargs: Any,
    ) -> BaseAgent:
        return cls(name=name, system_prompt=system_prompt, strategy=strategy, run_id=run_id, **kwargs)

    def card(self) -> AgentCard:
        return AgentCard(
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            capabilities=self.capabilities,
            tool_names=tuple(self._tool_name(tool) for tool in self._agent_tool_items),
            mcp_tool_names=self.mcp_tool_names(),
            mcp_server_names=tuple(handle.name for handle in self.mcp_servers()),
            modalities=self._card_modalities(),
            metadata=dict(self.metadata),
        )

    def add_tool(self, tool: object) -> BaseAgent:
        self._agent_tool_items = (*self._agent_tool_items, tool)
        try:
            self.tools = self.tools.add(tool)
        except TypeError:
            pass
        return self

    def as_tool(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> AgentTool:
        """Expose this agent as a BaseTool for registration in another agent's Tools catalog."""
        from vidbyte.tools.agent_tool import AgentTool

        return AgentTool(self, name=name, description=description)

    def tool_specs(self) -> tuple[ToolSpec, ...]:
        return self.tools.specs()

    def fork(
        self,
        *,
        name: str | None = None,
        strategy: BaseStrategy | None = None,
        runner: object | None = None,
        runners: Mapping[ModelModality | str, object] | None = None,
        tools: Sequence[object] | Tools | None = None,
        system_prompt: str | None = None,
        modality: ModelModality | str | None = None,
        metadata: dict[str, Any] | None = None,
        include_history: bool = False,
    ) -> BaseAgent:
        child = BaseAgent(
            name=name or self.name,
            strategy=strategy or self.strategy,
            runner=runner if runner is not None else self.runner,
            runners=runners if runners is not None else self.runners,
            tools=self._agent_tool_items if tools is None else tools,
            permission_policy=self.permission_policy,
            max_tool_rounds=self.max_tool_rounds,
            system_prompt=self.system_prompt if system_prompt is None else system_prompt,
            api_key=self.runner_config.api_key,
            provider=self.runner_config.provider,
            model_name=self.runner_config.model_name,
            modality=modality if modality is not None else self.modality,
            temperature=self.runner_config.temperature,
            run_id=self.runner_config.run_id,
            runner_options=dict(self.runner_config.options),
            description=self.description,
            capabilities=self.capabilities,
            metadata={**self.metadata, **dict(metadata or {})},
        )
        if include_history:
            child.history = list(self.history)
        return child

    async def receive(self, message: AgentMessage) -> None:
        self.history.append(message)

    async def generate_reply(
        self,
        message: str | AgentInput,
        *,
        modality: ModelModality | str | None = None,
        context: StrategyContext | None = None,
        history: Sequence[AgentMessage] = (),
        recipient: str = "orchestrator",
        **options: Any,
    ) -> AgentMessage:
        await self._ensure_mcp_connected()
        try:
            prompt, input_modality, input_metadata = self._normalize_input(message)
            selected_modality = ModalityDetector.resolve(
                requested=modality,
                input_modality=input_modality,
                default=self.modality,
            )
            if selected_modality is ModelModality.AUTO and self.runner_config.model_name:
                selected_modality = ModalityDetector.detect_modality(self.runner_config.model_name)
            if selected_modality is ModelModality.AUTO:
                selected_modality = ModelModality.TEXT
            runner = self._runner_for_modality(selected_modality)
            agent_context = self._build_context(
                prompt,
                context=context,
                history=history,
                input_metadata=input_metadata,
                modality=selected_modality,
            )
            if self.strategy is None:
                result = await self._run_without_strategy(prompt, agent_context, runner=runner, **options)
            else:
                result = await self.strategy.arun(
                    prompt,
                    runner=runner,
                    context=agent_context,
                    tools=self._agent_tool_items,
                    **options,
                )
        except Exception as exc:
            raise AgentExecutionError(
                f"Agent '{self.name}' failed to generate a reply.",
                details={"agent": self.name, "error_type": type(exc).__name__},
            ) from exc
        reply = AgentMessage(
            sender=self.name,
            recipient=recipient,
            content=result.output,
            metadata={
                "strategy": result.strategy_name,
                "modality": selected_modality.value,
                **dict(input_metadata),
                **dict(result.metadata),
            },
        )
        self.history.append(reply)
        return reply

    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        """Async ergonomic alias for generate_reply()."""
        return await self.generate_reply(message, **options)

    def run(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        """Run the agent from synchronous code."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.generate_reply(message, **options))
        raise AgentExecutionError("BaseAgent.run() cannot be called from an active event loop; use await arun().")

    def _build_context(
        self,
        message: str,
        *,
        context: StrategyContext | None,
        history: Sequence[AgentMessage],
        input_metadata: Mapping[str, Any] | None = None,
        modality: ModelModality | None = None,
    ) -> BaseAgentContext:
        merged_history = tuple(history) + tuple(self.history)
        metadata = dict(context.metadata if context else {})
        metadata.update(self.metadata)
        metadata.update(dict(input_metadata or {}))
        if modality is not None:
            metadata["modality"] = modality.value
        strategy_metadata = dict(context.strategy_metadata if context else {})
        strategy_metadata.update({"current_agent": self.name, "current_message": message})
        if modality is not None:
            strategy_metadata["modality"] = modality.value
        responses = tuple(context.responses) if context else ()
        return BaseAgentContext(
            system_prompt=context.system_prompt
            if context and context.system_prompt
            else self.system_prompt,
            agent_name=self.name,
            role=context.role if context else None,
            history=merged_history,
            file_paths=tuple(context.file_paths) if context else (),
            strategy_metadata=strategy_metadata,
            tool_calls=tuple(context.tool_calls) + tuple(self._tool_call_contexts) if context else tuple(self._tool_call_contexts),
            responses=responses,
            budget=context.budget if context else None,
            artifacts=tuple(context.artifacts) if context else (),
            memory=context.memory if context else None,
            permissions=context.permissions if context else None,
            metadata=metadata,
        )

    def _create_runner(self) -> object | None:
        if any(
            (
                self.runner_config.api_key,
                self.runner_config.provider,
                self.runner_config.model_name,
                self.runner_config.temperature is not None,
                self.runner_config.run_id,
                self.runner_config.options,
            )
        ):
            return ConfiguredAgentRunner(self.runner_config)
        return None

    async def _run_without_strategy(
        self,
        message: str,
        context: BaseAgentContext,
        *,
        runner: object | None = None,
        **options: Any,
    ) -> StrategyResult:
        if runner is None:
            raise AgentExecutionError("Agent without a strategy requires a runner.")
        if isinstance(runner, ConfiguredAgentRunner):
            raise AgentExecutionError(
                "ConfiguredAgentRunner stores primitive settings only; pass an executable runner when no strategy is set."
            )
        if len(self.tools):
            return await self._run_with_tools(runner, message, context=context, **options)
        response = await self._call_runner_once(runner, message, context=context, **options)
        return StrategyResult(
            output=self._runner_output_text(response),
            strategy_name="direct_runner",
            metadata=self._runner_output_metadata(response),
        )

    async def _run_with_tools(
        self,
        runner: object,
        message: str,
        *,
        context: BaseAgentContext,
        **options: Any,
    ) -> StrategyResult:
        provider = str(options.pop("provider", None) or self._runner_provider(runner))
        tool_schemas = self.tools.provider_schemas(provider)
        messages: list[dict[str, Any]] = [dict(item) for item in options.pop("messages", ())]
        call_contexts: list[ToolCallContext] = []

        for round_index in range(self.max_tool_rounds + 1):
            call_options = dict(options)
            call_options.setdefault("system", context.system_prompt)
            if tool_schemas:
                call_options.setdefault("tools", tool_schemas)
            if messages:
                call_options.setdefault("messages", tuple(messages))

            raw_result = await self._invoke_runner(runner, message, **call_options)
            tool_calls = ToolsFormatter.parse_tool_calls(raw_result, provider)
            if not tool_calls:
                self._tool_call_contexts.extend(call_contexts)
                return StrategyResult(
                    output=self._runner_output_text(raw_result),
                    strategy_name="direct_runner",
                    metadata={**self._tool_metadata(call_contexts), **self._runner_output_metadata(raw_result)},
                )

            if round_index >= self.max_tool_rounds:
                self._tool_call_contexts.extend(call_contexts)
                return StrategyResult(
                    output="Tool call limit reached before a final response.",
                    strategy_name="direct_runner",
                    metadata={**self._tool_metadata(call_contexts), "tool_round_limit_reached": True},
                )

            for call in tool_calls:
                context_record, result = await self._execute_agent_tool_call(call, provider=provider)
                call_contexts.append(context_record)
                messages.append(dict(ToolsFormatter.format_tool_result(call, result, provider)))

        self._tool_call_contexts.extend(call_contexts)
        return StrategyResult(
            output="Tool call limit reached before a final response.",
            strategy_name="direct_runner",
            metadata={**self._tool_metadata(call_contexts), "tool_round_limit_reached": True},
        )

    async def _execute_agent_tool_call(
        self,
        call: ToolCall,
        *,
        provider: str,
    ) -> tuple[ToolCallContext, ToolResult]:
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

    def _tool_metadata(self, contexts: Sequence[ToolCallContext]) -> dict[str, Any]:
        return {
            "tool_call_count": len(contexts),
            "tool_call_states": tuple(context.state.value for context in contexts),
            "tool_calls": tuple(contexts),
        }

    def _catalog_from_agent_tools(self, tools: Sequence[object]) -> Tools:
        catalog = Tools()
        for tool in tools:
            try:
                catalog = catalog.add(tool)
            except TypeError:
                continue
        return catalog

    async def _call_runner_once(
        self,
        runner: object,
        message: str,
        *,
        context: BaseAgentContext,
        **options: Any,
    ) -> object:
        call_options = dict(options)
        call_options.setdefault("system", context.system_prompt)
        return await self._invoke_runner(runner, message, **call_options)

    async def _invoke_runner(self, runner: object, message: str, **call_options: Any) -> object:
        arun = getattr(runner, "arun", None)
        if callable(arun):
            result = self._call_with_supported_kwargs(arun, message, call_options)
        else:
            run = getattr(runner, "run", None)
            if callable(run):
                result = self._call_with_supported_kwargs(run, message, call_options)
            elif callable(runner):
                result = self._call_with_supported_kwargs(runner, message, call_options)
            else:
                raise AgentExecutionError("Runner must define run(), arun(), or be callable.")
        if inspect.isawaitable(result):
            result = await result
        return result

    @staticmethod
    def _runner_output_text(result: object) -> str:
        text = getattr(result, "text", None)
        if text is not None:
            return str(text)
        images = getattr(result, "images", None)
        if images is not None:
            rendered = tuple(
                str(getattr(image, "url", "") or "")
                for image in tuple(images)
                if getattr(image, "url", None)
            )
            if rendered:
                return "\n".join(rendered)
            return f"[image generated: {len(tuple(images))}]"
        job_id = getattr(result, "job_id", None)
        status = getattr(result, "status", None)
        if job_id is not None and status is not None:
            return f"{job_id}: {status}"
        output = getattr(result, "output", None)
        if output is not None:
            return str(output)
        return str(result)

    @staticmethod
    def _runner_provider(runner: object) -> str:
        config = getattr(runner, "_config", None)
        provider = getattr(config, "provider", None)
        if provider is not None:
            return str(getattr(provider, "value", provider))
        model_name = getattr(runner, "model_name", None)
        if callable(model_name):
            try:
                return str(model_name())
            except Exception:
                return "openai"
        return "openai"

    @staticmethod
    def _runner_output_metadata(result: object) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        images = getattr(result, "images", None)
        if images is not None:
            metadata["image_count"] = len(tuple(images))
        job_id = getattr(result, "job_id", None)
        status = getattr(result, "status", None)
        if job_id is not None:
            metadata["job_id"] = str(job_id)
        if status is not None:
            metadata["status"] = str(status)
        return metadata

    def _normalize_input(
        self,
        message: str | AgentInput,
    ) -> tuple[str, ModelModality | str | None, Mapping[str, Any]]:
        if isinstance(message, AgentInput):
            return message.prompt, message.modality, message.metadata
        return message, None, {}

    def _runner_for_modality(self, modality: ModelModality) -> object | None:
        if modality in self.runners:
            return self.runners[modality]
        if self.runner is not None and not isinstance(self.runner, ConfiguredAgentRunner):
            return self.runner
        provider = self.runner_config.provider
        model_name = self.runner_config.model_name
        if provider and model_name:
            runner = ModalityDetector.create_runner(
                modality,
                provider=provider,
                model=model_name,
                api_key=self.runner_config.api_key,
                temperature=self.runner_config.temperature,
                **dict(self.runner_config.options),
            )
            self.runners[modality] = runner
            return runner
        return self.runner

    def _card_modalities(self) -> tuple[ModelModality, ...]:
        modalities = set(self.runners)
        if self.modality is not ModelModality.AUTO:
            modalities.add(self.modality)
        elif self.runner_config.provider and self.runner_config.model_name:
            detected = ModalityDetector.detect_modality(self.runner_config.model_name)
            modalities.add(detected if detected is not ModelModality.AUTO else ModelModality.TEXT)
        elif self.runner is not None or self.runner_config.provider or self.runner_config.model_name:
            modalities.add(ModelModality.TEXT)
        return tuple(sorted(modalities, key=lambda item: item.value))

    @staticmethod
    def _call_with_supported_kwargs(
        target: Callable[..., object],
        message: str,
        call_options: Mapping[str, Any],
    ) -> object:
        try:
            signature = inspect.signature(target)
        except (TypeError, ValueError):
            return target(message, **dict(call_options))
        if any(param.kind is inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
            return target(message, **dict(call_options))
        accepted = {
            name
            for name, param in signature.parameters.items()
            if param.kind in {inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        }
        filtered = {key: value for key, value in dict(call_options).items() if key in accepted}
        return target(message, **filtered)

    @staticmethod
    def _tool_name(tool: object) -> str:
        spec = getattr(tool, "spec", None)
        if callable(spec):
            try:
                tool_spec = spec()
            except Exception:
                return tool.__class__.__name__
            name = getattr(tool_spec, "name", None)
            if name:
                return str(name)
        return tool.__class__.__name__
