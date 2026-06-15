"""Context Protocol Header

Description:
    Defines the baseline agent implementation (BaseAgent) and configured runner wrappers.
Purpose:
    Combines prompting, tool registration, runtime state tracking, and execution
    into a unified developer-facing executable actor (the agent).
Architecture:
    - BaseAgent: Primary agent class inheriting MCP attachment capabilities.
    - ConfiguredAgentRunner: Simple payload carrier for backend runner parameters.
Relations:
    Inherits from McpAttachableMixin. Used by registries, harnesses, and multi-agent orchestration.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vidbyte.agents.mixins import McpAttachableMixin
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage
from vidbyte.context.manager import ContextManager
from vidbyte.context.window import ContextWindow, ContextWindowAlgorithm
from vidbyte.context.primitives import ContextItem
from vidbyte.context.handoff import Handoff, MinimalHandoff
from vidbyte.lib.agents import ModalityDetector
from vidbyte.lib.dataclasses.agents import AgentMetadata, AgentRunnerConfig, AgentRuntimeConfig
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.dataclasses.trace import TraceOption
from vidbyte.lib.enums import AgentRuntimeType, ModelModality, ModelProvider
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.tracing import NullTracer, TracerBase
from vidbyte.agents.runtimes.configs import ActorRuntime, LinearRuntime, MctsSearchRuntime
from vidbyte.middleware import AgentMiddleware
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCallContext, ToolSpec


class ConfiguredAgentRunner:
    """Runner placeholder created from primitive agent configuration."""

    def __init__(self, config: AgentRunnerConfig) -> None:
        self.config = config


class BaseAgent(McpAttachableMixin):
    """Reusable actor combining a system prompt, runner, and tools."""

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR,
        runner: object | None = None,
        runners: Mapping[ModelModality | str, object] | None = None,
        tools: Sequence[object] | Tools = (),
        permission_policy: PermissionPolicy | None = None,
        agent_loop_settings: AgentLoopSettings | None = None,
        max_tool_rounds: int | None = None,
        max_iterations: int | None = None,
        max_tokens: int | None = None,
        compaction_trigger_tokens: int | None = None,
        compaction_target_tokens: int | None = None,
        middleware: Sequence[AgentMiddleware] = (),
        api_key: str | None = None,
        provider: ModelProvider | str | None = None,
        model_name: str | None = None,
        modality: ModelModality | str = ModelModality.AUTO,
        temperature: float | None = None,
        run_id: str | None = None,
        runner_options: dict[str, Any] | None = None,
        description: str = "",
        capabilities: Sequence[str] = (),
        agent_metadata: AgentMetadata | None = None,
        context_items: Sequence[ContextItem] = (),
        context_manager: ContextManager | None = None,
        algorithm: ContextWindowAlgorithm | str | None = None,
        metadata: dict[str, Any] | None = None,
        tracer: type[TracerBase] | TracerBase | None = None,
        trace: type[TracerBase] | TracerBase | None = None,
        output_schema: type | Mapping[str, Any] | None = None,
        handoff: Handoff | None = None,
        trace_option: TraceOption | None = None,
    ) -> None:
        if not name:
            raise AgentExecutionError("Agent name cannot be empty.")
        if not system_prompt:
            raise AgentExecutionError("Agent system_prompt is required.")

        if isinstance(runtime, (LinearRuntime, MctsSearchRuntime, ActorRuntime)):
            self.runtime_type = runtime.runtime_type
            self.runtime_config_obj = runtime
        else:
            self.runtime_type = AgentRuntimeType(runtime)
            self.runtime_config_obj = None

        if self.runtime_type in (
            AgentRuntimeType.MCTS_SEARCH,
            AgentRuntimeType.ACTOR_MODEL,
            AgentRuntimeType.ACTOR_MODEL_P2P,
            AgentRuntimeType.ACTOR_MODEL_BROADCAST,
        ):
            if middleware:
                raise ConfigurationError(
                    f"Agent {name} uses non-linear runtime {self.runtime_type.value}, "
                    "which does not support middleware."
                )
            if trace_option is not None and trace_option.enabled:
                raise ConfigurationError(
                    f"Agent {name} uses non-linear runtime {self.runtime_type.value}, "
                    "which does not support continual tracing."
                )
            if algorithm is not None:
                resolved_algo = ContextWindow.resolve_algorithm(algorithm)
                if resolved_algo.name != "default":
                    raise ConfigurationError(
                        f"Agent {name} uses non-linear runtime {self.runtime_type.value}, "
                        "which does not support in-context learning algorithms."
                    )

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
        self.runner = runner if runner is not None else self._create_runner()
        self.runners = {
            ModalityDetector.coerce(runner_modality): runner_item
            for runner_modality, runner_item in dict(runners or {}).items()
        }
        self.modality = ModalityDetector.coerce(modality)
        self._agent_tool_items = tools.all() if isinstance(tools, Tools) else tuple(tools)
        self.tools = tools if isinstance(tools, Tools) else self._catalog_from_agent_tools(self._agent_tool_items)
        self.permission_policy = permission_policy or PermissionPolicy()
        effective_max_iterations = max_iterations if max_iterations is not None else max_tool_rounds
        self.agent_loop_settings = self._resolve_loop_settings(
            agent_loop_settings,
            max_iterations=effective_max_iterations,
            max_tokens=max_tokens,
            compaction_trigger_tokens=compaction_trigger_tokens,
            compaction_target_tokens=compaction_target_tokens,
        )
        self.runtime_config = self.agent_loop_settings.to_runtime_config()
        self.max_tool_rounds = self.agent_loop_settings.max_iterations
        self.system_prompt = system_prompt
        self.middleware = tuple(middleware)
        self.description = description or "General purpose agent."
        self.capabilities = tuple(capabilities)
        self.agent_metadata = agent_metadata or AgentMetadata()
        self.context_items = tuple(context_items)
        self.context_manager = context_manager
        self.algorithm = ContextWindow.resolve_algorithm(algorithm)
        self.metadata = dict(metadata or {})
        self.output_schema = output_schema
        self.history: list[AgentMessage] = []
        self._tool_call_contexts: list[ToolCallContext] = []
        self._active_prompt: str = ""
        self._handoff_spec: Handoff | None = handoff
        self.last_handoff: Handoff | None = None
        self.handoffs: list[Handoff] = []
        self._trace_option: TraceOption | None = trace_option
        self.last_trace: dict[str, Any] | None = None
        self.last_prompt: str = ""
        self.last_reply: AgentMessage | None = None
        for _tool in self._agent_tool_items:
            self._bind_agent_tool_context(_tool)

        self._tracer = self._resolve_tracer(tracer, trace)

        # MCP Attachable State
        self._mcp_handles = []
        self._pending_mcp_configs = []

    @classmethod
    def from_run_id(cls, run_id: str, *, name: str, system_prompt: str, **kwargs: Any) -> BaseAgent:
        return cls(name=name, system_prompt=system_prompt, run_id=run_id, **kwargs)

    @staticmethod
    def _resolve_loop_settings(agent_loop_settings: AgentLoopSettings | None, *, max_iterations: int | None, max_tokens: int | None, compaction_trigger_tokens: int | None, compaction_target_tokens: int | None) -> AgentLoopSettings:
        # Resolves the final AgentLoopSettings from either a pre-built object or flat kwargs.
        flat_params = {
            "max_iterations": max_iterations,
            "max_tokens": max_tokens,
            "compaction_trigger_tokens": compaction_trigger_tokens,
            "compaction_target_tokens": compaction_target_tokens,
        }
        active_flat = {k: v for k, v in flat_params.items() if v is not None}
        if agent_loop_settings is not None and active_flat:
            raise ConfigurationError(
                f"Pass either agent_loop_settings= or individual loop params ({', '.join(active_flat)}), not both."
            )
        if agent_loop_settings is not None:
            return agent_loop_settings
        return AgentLoopSettings(**flat_params)

    @staticmethod
    def _resolve_tracer(tracer: type[TracerBase] | TracerBase | None, trace: type[TracerBase] | TracerBase | None) -> TracerBase:
        # Normalizes the legacy tracer= argument and the public trace= alias.
        if tracer is not None and trace is not None:
            raise ConfigurationError("Pass either trace= or tracer=, not both.")
        selected = trace if trace is not None else tracer
        if selected is None:
            return NullTracer()
        if isinstance(selected, type):
            return selected()
        return selected

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
        self._bind_agent_tool_context(tool)
        return self

    def as_tool(self) -> object:
        """Return an AgentTool wrapping this agent for use by a parent agent.

        Raises ConfigurationError if agent_metadata fields are not filled in.
        """
        meta = self.agent_metadata
        if not meta.name or not meta.description or not meta.use_cases:
            raise ConfigurationError(
                "You need to fill in agent metadata (name, description, use_cases) "
                "if you want to use the agent as a tool.",
                details={
                    "agent": self.name,
                    "missing_name": not meta.name,
                    "missing_description": not meta.description,
                    "missing_use_cases": not meta.use_cases,
                },
            )
        from vidbyte.tools.agent_tool import AgentTool

        return AgentTool(self)

    def _bind_agent_tool_context(self, tool: object) -> None:
        """Bind this agent's live context getter to AgentTool instances."""
        from vidbyte.tools.agent_tool import AgentTool
        from vidbyte.tools.builtins.handoff import CreateHandoffTool
        from vidbyte.tools.builtins.mcp import AttachMcpServerTool

        if isinstance(tool, AgentTool):
            tool.bind_context_getter(lambda: (self._active_prompt, list(self.history)))
        if isinstance(tool, AttachMcpServerTool):
            tool.bind_agent(self)
        if isinstance(tool, CreateHandoffTool):
            tool.bind_agent(self)

    def tool_specs(self) -> tuple[ToolSpec, ...]:
        return self.tools.specs()

    def fork(
        self,
        *,
        name: str | None = None,
        runner: object | None = None,
        runners: Mapping[ModelModality | str, object] | None = None,
        tools: Sequence[object] | Tools | None = None,
        system_prompt: str | None = None,
        modality: ModelModality | str | None = None,
        metadata: dict[str, Any] | None = None,
        middleware: Sequence[AgentMiddleware] | None = None,
        context_items: Sequence[ContextItem] | None = None,
        context_manager: ContextManager | None = None,
        algorithm: ContextWindowAlgorithm | str | None = None,
        include_history: bool = False,
    ) -> BaseAgent:
        child = BaseAgent(
            name=name or self.name,
            runner=runner if runner is not None else self.runner,
            runners=runners if runners is not None else self.runners,
            tools=self._agent_tool_items if tools is None else tools,
            permission_policy=self.permission_policy,
            agent_loop_settings=self.agent_loop_settings,
            middleware=self.middleware if middleware is None else middleware,
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
            agent_metadata=self.agent_metadata,
            context_items=self.context_items if context_items is None else context_items,
            context_manager=self.context_manager if context_manager is None else context_manager,
            algorithm=self.algorithm if algorithm is None else algorithm,
            metadata={**self.metadata, **dict(metadata or {})},
            tracer=self._tracer,
            output_schema=self.output_schema,
            handoff=self._handoff_spec,
            trace_option=self._trace_option,
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
        context: BaseContext | None = None,
        history: Sequence[AgentMessage] = (),
        recipient: str = "orchestrator",
        **options: Any,
    ) -> AgentMessage:
        await self._ensure_mcp_connected()
        trace_ctx = None
        try:
            trace_metadata = dict(options.pop("trace_metadata", {}) or {})
            prompt, input_modality, input_metadata = self._normalize_input(message)
            input_context_items, input_context_manager = self._normalize_input_context(message)
            self._active_prompt = prompt
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
            trace_ctx = self._tracer.start_trace(
                "agent.run",
                agent_name=self.name,
                strategy="direct",
                prompt=self._safe_trace_value(prompt),
                provider=self._runner_provider(runner),
                model=self._runner_model_name(runner),
                metadata=self._safe_trace_value({**self.metadata, **dict(input_metadata), **trace_metadata}),
            )
            agent_context = self._build_context(
                prompt,
                context=context,
                history=history,
                input_metadata=input_metadata,
                modality=selected_modality,
                agentic_loop=True,
                input_context_items=input_context_items,
                input_context_manager=input_context_manager,
            )
            result = await self._run_direct(
                prompt,
                agent_context,
                runner=runner,
                modality=selected_modality,
                trace_context=trace_ctx,
                runtime_metadata={**self.metadata, **dict(input_metadata), **trace_metadata},
                **options,
            )
            if trace_ctx is not None:
                self._tracer.end_trace(trace_ctx, output=result.output)
        except Exception as exc:
            if trace_ctx is not None:
                self._tracer.end_trace(trace_ctx, error=exc)
            self._active_prompt = ""
            raise AgentExecutionError(
                f"Agent '{self.name}' failed to generate a reply.",
                details={"agent": self.name, "error_type": type(exc).__name__},
            ) from exc
        self._active_prompt = ""
        metadata: dict[str, Any] = {
            "strategy": result.strategy_name,
            "modality": selected_modality.value,
            **dict(input_metadata),
            **dict(result.metadata),
        }
        if result.structured is not None:
            metadata["structured"] = result.structured
        reply = AgentMessage(
            sender=self.name,
            recipient=recipient,
            content=result.output,
            metadata=metadata,
        )
        self.history.append(reply)
        self.last_prompt = prompt
        self.last_reply = reply
        if self._trace_option is not None and self._trace_option.enabled:
            trace_artifact = metadata.get("trace")
            self.last_trace = dict(trace_artifact) if isinstance(trace_artifact, Mapping) else None
        if self._handoff_spec is not None:
            await self._run_auto_handoff(metadata)
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

    async def handoff(self, spec: Handoff | None = None, *, by: "BaseAgent | None" = None) -> Handoff:
        """Produce a structured handoff document describing this agent's most recent run."""
        from vidbyte.agents.handoff import HandoffAgent
        resolved = spec or self._handoff_spec or MinimalHandoff()
        generator = by or HandoffAgent.from_source_agent(self, resolved)
        return await generator.generate_handoff(HandoffAgent.render_source_run(self))

    def record_handoff(self, handoff: Handoff) -> None:
        """Append a produced handoff to the run's collection and sync it to the context registry."""
        self.handoffs.append(handoff)
        self.last_handoff = handoff
        self._sync_handoff_primitive(handoff)

    def _sync_handoff_primitive(self, handoff: Handoff) -> None:
        """Upsert the handoff into the context manager when one is configured and an id exists."""
        if self.context_manager is None or not handoff.primitive_id:
            return
        try:
            self.context_manager.upsert(handoff)
        except ValueError:
            return

    async def _run_auto_handoff(self, metadata: dict[str, Any]) -> None:
        # Generate the configured handoff after a run and record it without breaking the primary reply.
        from vidbyte.agents.handoff import HandoffAgent
        try:
            produced = await HandoffAgent.run_auto_handoff(self, self._handoff_spec)
            self.record_handoff(produced)
            metadata["handoff"] = produced
        except Exception as exc:
            metadata["handoff_error"] = repr(exc)
            self.last_handoff = None

    def _build_context(
        self,
        message: str,
        *,
        context: BaseContext | None,
        history: Sequence[AgentMessage],
        input_metadata: Mapping[str, Any] | None = None,
        modality: ModelModality | None = None,
        agentic_loop: bool = True,
        input_context_items: Sequence[ContextItem] = (),
        input_context_manager: ContextManager | None = None,
    ) -> BaseAgentContext:
        return self._runtime().build_context(
            message,
            base_context=context,
            history=history,
            agent_history=self.history,
            agent_metadata=self.metadata,
            existing_tool_calls=self._tool_call_contexts,
            input_metadata=input_metadata,
            modality=modality,
            agentic_loop=agentic_loop,
            context_items=self._merged_context_items(input_context_items),
            context_manager=self._merged_context_manager(input_context_manager),
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

    async def _run_direct(
        self,
        message: str,
        context: BaseAgentContext,
        *,
        runner: object | None = None,
        modality: ModelModality = ModelModality.TEXT,
        trace_context: object | None = None,
        runtime_metadata: Mapping[str, Any] | None = None,
        **options: Any,
    ) -> AgentResult:
        if runner is None:
            raise AgentExecutionError("Agent requires a runner.")
        if isinstance(runner, ConfiguredAgentRunner):
            raise AgentExecutionError(
                "ConfiguredAgentRunner stores primitive settings only; pass an executable runner."
            )
        if modality is not ModelModality.TEXT:
            raw_result = await self._call_runner_once(runner, message, context=context, **options)
            return AgentResult(
                output=self._runner_output_text(raw_result),
                strategy_name="direct_runner",
                metadata=self._runner_output_metadata(raw_result),
            )
        provider = str(options.pop("provider", None) or self._runner_provider(runner))
        handle = RunnerHandle(
            runner=runner,
            provider=provider,
            invoke=self._invoke_runner,
            extract_text=self._runner_output_text,
            extract_metadata=self._runner_output_metadata,
        )
        result = await self._runtime().arun(
            message,
            handle=handle,
            context=context,
            metadata=runtime_metadata,
            options=options,
            trace_context=trace_context,
        )
        self._record_tool_contexts(result)
        return result

    async def _run_with_tools(
        self,
        runner: object,
        message: str,
        *,
        context: BaseAgentContext,
        **options: Any,
    ) -> AgentResult:
        provider = str(options.pop("provider", None) or self._runner_provider(runner))
        handle = RunnerHandle(
            runner=runner,
            provider=provider,
            invoke=self._invoke_runner,
            extract_text=self._runner_output_text,
            extract_metadata=self._runner_output_metadata,
        )
        result = await self._runtime().arun(
            message,
            handle=handle,
            context=context,
            metadata=self.metadata,
            options=options,
        )
        self._record_tool_contexts(result)
        return result

    def _record_tool_contexts(self, result: AgentResult) -> None:
        contexts = result.metadata.get("tool_calls", ())
        self._tool_call_contexts.extend(
            context
            for context in tuple(contexts)
            if isinstance(context, ToolCallContext)
        )

    def _runtime(self) -> Any:
        from vidbyte.lib.registries.runtimes import RuntimeRegistry
        runtime_cls = RuntimeRegistry.resolve(self.runtime_type)

        kwargs: dict[str, Any] = {}
        if self.runtime_type in (
            AgentRuntimeType.ACTOR_MODEL,
            AgentRuntimeType.ACTOR_MODEL_P2P,
            AgentRuntimeType.ACTOR_MODEL_BROADCAST,
        ):
            if isinstance(self.runtime_config_obj, ActorRuntime):
                kwargs = {
                    "dynamic_actors": self.runtime_config_obj.dynamic_actors,
                    "max_loop": self.runtime_config_obj.max_loop,
                    "termination_mode": self.runtime_config_obj.termination_mode,
                    "worker_model": self.runtime_config_obj.worker_model,
                    "include_actors": self.runtime_config_obj.include_actors,
                }
            else:
                kwargs = {
                    "dynamic_actors": False,
                    "max_loop": 20,
                    "termination_mode": "coordinator",
                    "worker_model": None,
                    "include_actors": None,
                }

        return runtime_cls(
            agent_name=self.name,
            system_prompt=self.system_prompt,
            tools=self.tools,
            permission_policy=self.permission_policy,
            config=self.runtime_config,
            tracer=self._tracer,
            middleware=self._runtime_middleware(),
            run_id=self.runner_config.run_id,
            algorithm=self.algorithm,
            context_manager=self.context_manager,
            output_schema=self.output_schema,
            **kwargs,
        )

    def _runtime_middleware(self) -> tuple[AgentMiddleware, ...]:
        # Appends the continual trace middleware to the user middleware when tracing is enabled.
        if self._trace_option is None or not self._trace_option.enabled:
            return self.middleware
        from vidbyte.middleware.continual_trace import ContinualTraceMiddleware
        return (*self.middleware, ContinualTraceMiddleware(self._trace_option, source_agent=self))

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
        return str(model_name) if model_name is not None else None

    @classmethod
    def _safe_trace_value(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: cls._safe_trace_value(item) for key, item in value.items() if not cls._is_secret_trace_key(str(key))}
        if isinstance(value, tuple):
            return tuple(cls._safe_trace_value(item) for item in value)
        if isinstance(value, list):
            return [cls._safe_trace_value(item) for item in value]
        return value

    @staticmethod
    def _is_secret_trace_key(key: str) -> bool:
        upper = key.upper()
        return any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH"))

    @staticmethod
    def _runner_output_metadata(result: object) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        response_metadata = getattr(result, "metadata", None)
        if isinstance(response_metadata, Mapping):
            metadata.update(dict(response_metadata))
        raw = getattr(result, "raw", None)
        if isinstance(raw, Mapping) and "usage" in raw and "usage" not in metadata:
            metadata["usage"] = raw["usage"]
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

    def _normalize_input_context(
        self,
        message: str | AgentInput,
    ) -> tuple[tuple[ContextItem, ...], ContextManager | None]:
        if isinstance(message, AgentInput):
            return tuple(message.context_items), message.context_manager
        return (), None

    def _merged_context_items(self, input_context_items: Sequence[ContextItem]) -> tuple[ContextItem, ...]:
        return (*self.context_items, *tuple(input_context_items))

    def _merged_context_manager(self, input_context_manager: ContextManager | None) -> ContextManager | None:
        if self.context_manager is None and input_context_manager is None:
            return None
        manager = ContextManager()
        if self.context_manager is not None:
            manager.extend(self.context_manager.items())
        if input_context_manager is not None:
            manager.extend(input_context_manager.items())
        return manager

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
