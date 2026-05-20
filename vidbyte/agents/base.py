from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vidbyte.agents.types import AgentCard, AgentMessage, AgentRole
from vidbyte.lib.dataclasses.agents import AgentRunnerConfig
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.prompts.registry import prompt_registry
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyContext
from vidbyte.tools import ToolSpec


class ConfiguredAgentRunner:
    """Runner placeholder created from primitive agent configuration."""

    def __init__(self, config: AgentRunnerConfig) -> None:
        self.config = config


class BaseAgent:
    """Reusable actor combining a strategy, runner, role, and tools."""

    def __init__(self, *, name: str, strategy: BaseStrategy, runner: object | None = None, tools: Sequence[object] = (), role: AgentRole = "worker", system_prompt: str = "", api_key: str | None = None, model_name: str | None = None, temperature: float | None = None, run_id: str | None = None, runner_options: dict[str, Any] | None = None, description: str = "", capabilities: Sequence[str] = (), metadata: dict[str, Any] | None = None) -> None:
        if not name:
            raise AgentExecutionError("Agent name cannot be empty.")
        if strategy is None:
            raise AgentExecutionError("Agent strategy is required.")
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
        self.tools = tuple(tools)
        self.role = role
        self.system_prompt = system_prompt or self._default_system_prompt(role)
        self.description = description or "General purpose agent."
        self.capabilities = tuple(capabilities)
        self.metadata = dict(metadata or {})
        self.history: list[AgentMessage] = []

    @classmethod
    def from_run_id(cls, run_id: str, *, name: str, strategy: BaseStrategy, **kwargs: Any) -> "BaseAgent":
        return cls(name=name, strategy=strategy, run_id=run_id, **kwargs)

    def card(self) -> AgentCard:
        return AgentCard(
            name=self.name,
            role=self.role,
            description=self.description,
            system_prompt=self.system_prompt,
            capabilities=self.capabilities,
            tool_names=tuple(self._tool_name(tool) for tool in self.tools),
            metadata=dict(self.metadata),
        )

    def add_tool(self, tool: object) -> "BaseAgent":
        self.tools = (*self.tools, tool)
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
            specs.append(tool_spec if isinstance(tool_spec, ToolSpec) else ToolSpec(name=str(getattr(tool_spec, "name", tool.__class__.__name__)), description=str(getattr(tool_spec, "description", ""))))
        return tuple(specs)

    def fork(self, *, name: str | None = None, strategy: BaseStrategy | None = None, runner: object | None = None, tools: Sequence[object] | None = None, role: AgentRole | None = None, system_prompt: str | None = None, metadata: dict[str, Any] | None = None, include_history: bool = False) -> "BaseAgent":
        child = BaseAgent(
            name=name or self.name,
            strategy=strategy or self.strategy,
            runner=runner if runner is not None else self.runner,
            tools=self.tools if tools is None else tools,
            role=role or self.role,
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

    async def generate_reply(self, message: str, *, context: StrategyContext | None = None, history: Sequence[AgentMessage] = (), recipient: str = "orchestrator", **options: Any) -> AgentMessage:
        agent_context = self._build_context(message, context=context, history=history)
        try:
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
                details={"agent": self.name, "role": self.role, "error_type": type(exc).__name__},
            ) from exc
        reply = AgentMessage(
            sender=self.name,
            recipient=recipient,
            content=result.output,
            metadata={"strategy": result.strategy_name, **dict(result.metadata)},
        )
        self.history.append(reply)
        return reply

    def _build_context(self, message: str, *, context: StrategyContext | None, history: Sequence[AgentMessage]) -> StrategyContext:
        merged_history = tuple(history) + tuple(self.history)
        metadata = dict(context.metadata if context else {})
        metadata.update(self.metadata)
        strategy_metadata = dict(context.strategy_metadata if context else {})
        strategy_metadata.update({"current_agent": self.name, "current_role": self.role, "current_message": message})
        responses = tuple(context.responses) if context else ()
        return StrategyContext(
            system_prompt=context.system_prompt if context and context.system_prompt else self.system_prompt,
            agent_name=self.name,
            role=self.role,
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
        if any((self.runner_config.api_key, self.runner_config.model_name, self.runner_config.temperature is not None, self.runner_config.run_id, self.runner_config.options)):
            return ConfiguredAgentRunner(self.runner_config)
        return None

    @staticmethod
    def _default_system_prompt(role: AgentRole) -> str:
        import vidbyte.prompts.prompts  # noqa: F401

        try:
            return prompt_registry.get(f"agent_role.{role}").export()
        except KeyError:
            return ""

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
