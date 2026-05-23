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
from typing import Any

from vidbyte.agents.mixins import McpAttachableMixin
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage
from vidbyte.lib.dataclasses.agents import AgentRunnerConfig
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.lib.runners import coerce_modality, create_runner_for_modality, resolve_modality
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import BaseAgentContext, StrategyContext, StrategyResult
from vidbyte.tools import ToolSpec


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
        tools: Sequence[object] = (),
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
            coerce_modality(runner_modality): runner_item
            for runner_modality, runner_item in dict(runners or {}).items()
        }
        self.modality = coerce_modality(modality)
        self.tools = list(tools)
        self.system_prompt = system_prompt
        self.description = description or "General purpose agent."
        self.capabilities = tuple(capabilities)
        self.metadata = dict(metadata or {})
        self.history: list[AgentMessage] = []
        
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
            tool_names=tuple(self._tool_name(tool) for tool in self.tools),
            mcp_tool_names=self.mcp_tool_names(),
            mcp_server_names=tuple(handle.name for handle in self.mcp_servers()),
            modalities=self._card_modalities(),
            metadata=dict(self.metadata),
        )

    def add_tool(self, tool: object) -> BaseAgent:
        self.tools = [*self.tools, tool]
        return self

    def tool_specs(self) -> tuple[ToolSpec, ...]:
        specs: list[ToolSpec] = []
        for tool in self.tools:
            spec = getattr(tool, "spec", None)
            if callable(spec):
                try:
                    tool_spec = spec()
                except Exception:
                    tool_spec = ToolSpec(name=tool.__class__.__name__, description="")
            else:
                tool_spec = ToolSpec(name=tool.__class__.__name__, description="")
            specs.append(
                tool_spec
                if isinstance(tool_spec, ToolSpec)
                else ToolSpec(
                    name=str(getattr(tool_spec, "name", tool.__class__.__name__)),
                    description=str(getattr(tool_spec, "description", "")),
                )
            )
        return tuple(specs)

    def fork(
        self,
        *,
        name: str | None = None,
        strategy: BaseStrategy | None = None,
        runner: object | None = None,
        runners: Mapping[ModelModality | str, object] | None = None,
        tools: Sequence[object] | None = None,
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
            tools=self.tools if tools is None else tools,
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
            selected_modality = resolve_modality(
                requested=modality,
                input_modality=input_modality,
                default=self.modality,
            )
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
                    tools=self.tools,
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
        return await self.generate_reply(message, **options)

    def run(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.generate_reply(message, **options))
        raise AgentExecutionError("Use 'await agent.arun(...)' inside an active event loop.")

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
            tool_calls=tuple(context.tool_calls) if context else (),
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
        response = await self._call_runner_once(runner, message, context=context, **options)
        return StrategyResult(
            output=self._runner_output_text(response),
            strategy_name="direct_runner",
            metadata=self._runner_output_metadata(response),
        )

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
            runner = create_runner_for_modality(
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
