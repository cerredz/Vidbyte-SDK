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

import inspect
from collections.abc import Sequence
from typing import Any

from vidbyte.agents.mixins import McpAttachableMixin
from vidbyte.agents.types import AgentCard, AgentMessage
from vidbyte.lib.dataclasses.agents import AgentRunnerConfig
from vidbyte.lib.errors import AgentExecutionError
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
        tools: Sequence[object] = (),
        api_key: str | None = None,
        model_name: str | None = None,
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
            model_name=model_name,
            temperature=temperature,
            run_id=run_id,
            options=dict(runner_options or {}),
        )
        self.name = name
        self.strategy = strategy
        self.runner = runner if runner is not None else self._create_runner()
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
        tools: Sequence[object] | None = None,
        system_prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
        include_history: bool = False,
    ) -> BaseAgent:
        child = BaseAgent(
            name=name or self.name,
            strategy=strategy or self.strategy,
            runner=runner if runner is not None else self.runner,
            tools=self.tools if tools is None else tools,
            system_prompt=self.system_prompt if system_prompt is None else system_prompt,
            api_key=self.runner_config.api_key,
            model_name=self.runner_config.model_name,
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
        message: str,
        *,
        context: StrategyContext | None = None,
        history: Sequence[AgentMessage] = (),
        recipient: str = "orchestrator",
        **options: Any,
    ) -> AgentMessage:
        await self._ensure_mcp_connected()
        agent_context = self._build_context(message, context=context, history=history)
        try:
            if self.strategy is None:
                result = await self._run_without_strategy(message, agent_context, **options)
            else:
                result = await self.strategy.arun(
                    message,
                    runner=self.runner,
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
            metadata={"strategy": result.strategy_name, **dict(result.metadata)},
        )
        self.history.append(reply)
        return reply

    def _build_context(
        self,
        message: str,
        *,
        context: StrategyContext | None,
        history: Sequence[AgentMessage],
    ) -> BaseAgentContext:
        merged_history = tuple(history) + tuple(self.history)
        metadata = dict(context.metadata if context else {})
        metadata.update(self.metadata)
        strategy_metadata = dict(context.strategy_metadata if context else {})
        strategy_metadata.update({"current_agent": self.name, "current_message": message})
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
        **options: Any,
    ) -> StrategyResult:
        runner = self.runner
        if runner is None:
            raise AgentExecutionError("Agent without a strategy requires a runner.")
        if isinstance(runner, ConfiguredAgentRunner):
            raise AgentExecutionError(
                "ConfiguredAgentRunner stores primitive settings only; pass an executable runner when no strategy is set."
            )
        output = await self._call_runner_once(runner, message, context=context, **options)
        return StrategyResult(output=output, strategy_name="direct_runner")

    async def _call_runner_once(
        self,
        runner: object,
        message: str,
        *,
        context: BaseAgentContext,
        **options: Any,
    ) -> str:
        call_options = dict(options)
        call_options.setdefault("system", context.system_prompt)
        arun = getattr(runner, "arun", None)
        if callable(arun):
            result = arun(message, **call_options)
        else:
            run = getattr(runner, "run", None)
            if callable(run):
                result = run(message, **call_options)
            elif callable(runner):
                result = runner(message, **call_options)
            else:
                raise AgentExecutionError("Runner must define run(), arun(), or be callable.")
        if inspect.isawaitable(result):
            result = await result
        return self._runner_output_text(result)

    @staticmethod
    def _runner_output_text(result: object) -> str:
        text = getattr(result, "text", None)
        if text is not None:
            return str(text)
        output = getattr(result, "output", None)
        if output is not None:
            return str(output)
        return str(result)

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
