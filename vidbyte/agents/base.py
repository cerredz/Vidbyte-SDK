"""Context Protocol Header

Description:
    Defines the baseline agent implementation (BaseAgent).
Purpose:
    Combines prompting, tool registration, runtime state tracking, and execution
    into a unified developer-facing executable actor (the agent), including its
    cooperative pause API.
Architecture:
    - BaseAgent: Primary agent class inheriting MCP attachment capabilities and
      exposing shared async execution and pause behavior.
Relations:
    Inherits from McpAttachableMixin. Used by registries, harnesses, and
    multi-agent orchestration. Agent-bound built-ins are wired in
    _bind_agent_tool_context().
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.agents.mixins import McpAttachableMixin
from vidbyte.agents.pricing import UsageRollup, UsageTracker
from vidbyte.agents.runtimes.configs import (
    ActorRuntime,
    LinearRuntime,
    MctsSearchRuntime,
)
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage
from vidbyte.context.handoff import Handoff, MinimalHandoff
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.context.window import ContextWindow, ContextWindowAlgorithm
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.dataclasses.agents import (
    AgentForkSettings,
    AgentMetadata,
    AgentRunnerConfig,
    AgentRuntimeConfig,
    FallbackModel,
    PauseDuration,
)
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.sessions import SESSION_SCHEMA_VERSION, RunState
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.dataclasses.trace import TraceOption
from vidbyte.lib.enums import AgentRuntimeType, ModelProvider
from vidbyte.lib.errors import (
    AgentExecutionError,
    ConfigurationError,
    OutputSchemaViolationError,
)
from vidbyte.lib.runners import Runner
from vidbyte.lib.tracing import NullTracer, TracerBase
from vidbyte.middleware import AgentMiddleware
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCallContext, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.contract import AgentLoopSettingsOutputContract
    from vidbyte.agents.settings import AgentFallbackSettings
    from vidbyte.sessions.session import Session
    from vidbyte.sessions.store import SessionStore


class BaseAgent(McpAttachableMixin):
    """Reusable actor combining a system prompt, model identity, and tools."""

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR,
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
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        run_id: str | None = None,
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
        fallback: Sequence[str | FallbackModel] | AgentFallbackSettings | None = None,
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
            if fallback is not None:
                raise ConfigurationError(
                    f"Agent {name} uses non-linear runtime {self.runtime_type.value}, "
                    "which does not support model fallback."
                )
            if output_schema is not None:
                # These runtimes never populate AgentResult.structured, so a schema they silently
                # ignored would fail every run once the guarantee is enforced. Reject it up front.
                raise ConfigurationError(
                    f"Agent {name} uses non-linear runtime {self.runtime_type.value}, "
                    "which does not support output_schema."
                )

        if model_name is not None and not isinstance(model_name, str):
            raise ConfigurationError(
                "BaseAgent model_name must be a single model name string; "
                "use AggregateAgent for multi-model aggregation.",
                details={"agent": name, "model_name_type": type(model_name).__name__},
            )

        provider_str = str(provider.value if isinstance(provider, ModelProvider) else provider) if provider is not None else None
        self.runner_config = AgentRunnerConfig(
            api_key=api_key,
            provider=provider_str,
            model_name=model_name,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
        )
        self.name = name
        self._fallback_spec = fallback
        from vidbyte.agents.fallback import AgentFallback
        self.fallback = AgentFallback.from_spec(fallback, runner_config=self.runner_config, agent_name=name)
        self._runner_cache: dict[str, object] = {}
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
        if self.agent_loop_settings.tool_error_policy is not None and self.runtime_type in (
            AgentRuntimeType.MCTS_SEARCH,
            AgentRuntimeType.ACTOR_MODEL,
            AgentRuntimeType.ACTOR_MODEL_P2P,
            AgentRuntimeType.ACTOR_MODEL_BROADCAST,
        ):
            raise ConfigurationError(
                f"Agent {name} uses non-linear runtime {self.runtime_type.value}, "
                "which does not support tool_error_policy middleware."
            )
        if self.agent_loop_settings.tool_settings is not None and self.runtime_type in (
            AgentRuntimeType.MCTS_SEARCH,
            AgentRuntimeType.ACTOR_MODEL,
            AgentRuntimeType.ACTOR_MODEL_P2P,
            AgentRuntimeType.ACTOR_MODEL_BROADCAST,
        ):
            raise ConfigurationError(
                f"Agent {name} uses non-linear runtime {self.runtime_type.value}, "
                "which does not support tool_settings."
            )
        if self.agent_loop_settings.output_contract.active() and self.runtime_type is not AgentRuntimeType.LINEAR:
            raise ConfigurationError(
                f"Agent {name} uses non-linear runtime {self.runtime_type.value}, "
                "which does not support output contracts."
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
        # Usage/cost tracking is built from the agent's own model identity; the
        # default rate table prices every model the agent can run. Per-call usage
        # is observable mid-run through MiddlewareContext.model_usage.
        self._usage_tracker = UsageTracker()
        self._behavior_view: Any = None
        self._active_session: Session | None = None
        self._queued_prompts: list[str] = []
        self._draining_queued_prompts: bool = False
        self.last_queued_replies: list[AgentMessage] = []
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

    @property
    def behavior(self) -> Any:
        # Lazily builds and caches a Behavior facade over the agent's last run.
        from vidbyte.evals.behavior import Behavior

        if self._behavior_view is None:
            self._behavior_view = Behavior(self)
        return self._behavior_view

    @property
    def session(self) -> Session | None:
        # Return the durable session currently bound to this agent, if any.
        return self._active_session

    def persist(self, *, store: SessionStore | None = None, **kwargs: Any) -> Session:
        # Attach this agent to a durable Session using the agent-native entry point.
        from vidbyte.sessions.session import Session

        return Session(self, store=store, **kwargs)

    def bind_session(self, session: Session) -> BaseAgent:
        # Bind this agent and all carried session-builtin tools to a durable session.
        self._active_session = session
        for tool in self._agent_tool_items:
            self._bind_session_tool(tool)
        return self

    def _bind_agent_tool_context(self, tool: object) -> None:
        """Bind this agent's live context getter to AgentTool instances."""
        from vidbyte.tools.agent_tool import AgentTool
        from vidbyte.tools.builtins.fork import ForkConversationTool
        from vidbyte.tools.builtins.handoff import CreateHandoffTool
        from vidbyte.tools.builtins.mcp import AttachMcpServerTool
        from vidbyte.tools.builtins.pause import PauseAgentTool
        from vidbyte.tools.builtins.run_prompts_sequentially import (
            RunPromptsSequentiallyTool,
        )

        if isinstance(tool, AgentTool):
            tool.bind_context_getter(lambda: (self._active_prompt, list(self.history)))
        if isinstance(tool, AttachMcpServerTool):
            tool.bind_agent(self)
        if isinstance(tool, CreateHandoffTool):
            tool.bind_agent(self)
        if isinstance(tool, ForkConversationTool):
            tool.bind_agent(self)
        if isinstance(tool, RunPromptsSequentiallyTool):
            tool.bind_agent(self)
        if isinstance(tool, PauseAgentTool):
            tool.bind_agent(self)
        self._bind_session_tool(tool)

    def _bind_session_tool(self, tool: object) -> None:
        # Bind a session-builtin tool to this agent's active session when one is attached.
        binder = getattr(tool, "bind_session", None)
        if not callable(binder):
            return
        if self._active_session is not None:
            binder(self._active_session)

    def _notify_session(self, reply: AgentMessage) -> None:
        # Ask the bound session to record this completed turn without letting persistence alter the reply path.
        session = self._active_session
        if session is None:
            return
        record_turn = getattr(session, "record_turn", None)
        if not callable(record_turn):
            return
        try:
            record_turn(reply)
        except Exception as exc:
            if isinstance(reply.metadata, dict):
                reply.metadata["__session_error__"] = f"{type(exc).__name__}: {exc}"

    def tool_specs(self) -> tuple[ToolSpec, ...]:
        return self.tools.specs()

    def fork(self, settings: AgentForkSettings | None = None) -> BaseAgent:
        # Forks this agent into an isolated child branch; all fork logic lives in AgentForker.
        from vidbyte.agents.fork import AgentForker

        return AgentForker.fork(self, settings if settings is not None else AgentForkSettings())

    def export_state(self) -> RunState:
        """Capture a serializable RunState snapshot of this agent (no secrets, no live objects)."""
        from vidbyte.sessions.serialization import SessionSerializer
        serializer = SessionSerializer()
        return RunState(
            schema_version=SESSION_SCHEMA_VERSION,
            agent_name=self.name,
            system_prompt=self.system_prompt,
            description=self.description,
            capabilities=tuple(self.capabilities),
            provider=self.runner_config.provider,
            model_name=self.runner_config.model_name,
            temperature=self.runner_config.temperature,
            runtime_type=self.runtime_type.value,
            runtime_config=self._export_runtime_config(),
            algorithm=self.algorithm.name,
            metadata=dict(self.metadata),
            agent_metadata=self._export_agent_metadata(),
            tool_names=tuple(self._tool_name(tool) for tool in self._agent_tool_items),
            history=tuple(serializer.message_to_dict(message) for message in self.history),
            run_id=self.runner_config.run_id,
            loop_settings=self._export_loop_settings(),
            aggregate_plan={},
            context_summary=self._export_context_summary(),
            trace_option=self._export_trace_option(),
            output_schema=self._export_output_schema(),
        )

    @classmethod
    def restore(cls, state: RunState, *, tools: Sequence[object] = (), middleware: Sequence[AgentMiddleware] = (), tracer: object | None = None, trace: object | None = None, output_schema: object | None = None) -> BaseAgent:
        """Rebuild a live agent from a RunState, re-supplying non-serializable parts (the rehydration contract)."""
        from vidbyte.sessions.serialization import SessionSerializer
        serializer = SessionSerializer()
        agent_metadata = AgentMetadata(**{key: str(state.agent_metadata.get(key, "")) for key in ("name", "description", "use_cases")})
        child = cls(
            name=state.agent_name,
            system_prompt=state.system_prompt,
            runtime=cls._restore_runtime(state),
            tools=tools,
            middleware=middleware,
            provider=state.provider,
            model_name=state.model_name,
            temperature=state.temperature,
            run_id=state.run_id,
            agent_loop_settings=cls._restore_loop_settings(state),
            description=state.description,
            capabilities=tuple(state.capabilities),
            agent_metadata=agent_metadata,
            algorithm=None if state.algorithm in ("", "default") else state.algorithm,
            metadata=dict(state.metadata),
            tracer=tracer,
            trace=trace,
            output_schema=output_schema,
        )
        child.history = [serializer.message_from_dict(item) for item in state.history]
        cls._record_resume_tool_mismatch(child, state.tool_names)
        return child

    def _export_runtime_config(self) -> dict[str, Any]:
        # Capture runtime budgets plus actor-runtime settings when present.
        config: dict[str, Any] = {
            "max_iterations": self.runtime_config.max_iterations,
            "max_tokens": self.runtime_config.max_tokens,
            "max_tool_calls": self.runtime_config.max_tool_calls,
            "compaction_trigger_tokens": self.runtime_config.compaction_trigger_tokens,
            "compaction_target_tokens": self.runtime_config.compaction_target_tokens,
        }
        if isinstance(self.runtime_config_obj, ActorRuntime):
            config.update(
                {
                    "dynamic_actors": self.runtime_config_obj.dynamic_actors,
                    "max_loop": self.runtime_config_obj.max_loop,
                    "termination_mode": self.runtime_config_obj.termination_mode,
                    "worker_model": self.runtime_config_obj.worker_model,
                }
            )
        return config

    def _export_loop_settings(self) -> dict[str, Any]:
        # Preserve every current AgentLoopSettings field, including those not understood by AgentRuntimeConfig.
        fields = (
            "max_iterations",
            "max_tokens",
            "max_tool_calls",
            "max_queued_prompts",
            "max_parallel_tool_calls",
            "max_retries",
            "timeout_seconds",
            "context_window_budget",
            "compaction_trigger_tokens",
            "compaction_target_tokens",
            "allowed_tools",
        )
        values = {name: getattr(self.agent_loop_settings, name, None) for name in fields}
        if isinstance(values.get("allowed_tools"), tuple):
            values["allowed_tools"] = list(values["allowed_tools"])
        return {key: value for key, value in values.items() if value is not None}

    def _export_context_summary(self) -> dict[str, Any]:
        # Record resumable context metadata without serializing live context objects.
        return {
            "context_item_count": len(self.context_items),
            "has_context_manager": self.context_manager is not None,
            "algorithm": self.algorithm.name,
        }

    def _export_trace_option(self) -> dict[str, Any]:
        # Capture trace-option primitives when the object exposes them; omit live tracer state.
        option = self._trace_option
        if option is None:
            return {}
        return {
            "mode": option.mode.value,
            "schema_name": option.schema.name,
            "schema_description": option.schema.description,
            "schema_fields": {
                name: {"description": field.description, "type": field.type.value}
                for name, field in option.schema.fields.items()
            },
            "every_n_iterations": option.every_n_iterations,
            "max_trace_iterations": option.max_trace_iterations,
        }

    def _export_output_schema(self) -> dict[str, Any] | None:
        # Store a marker for output_schema so restore callers know whether to re-supply one.
        if self.output_schema is None:
            return None
        if isinstance(self.output_schema, Mapping):
            return {"kind": "mapping", "schema": dict(self.output_schema)}
        return {"kind": "type", "name": getattr(self.output_schema, "__name__", type(self.output_schema).__name__)}

    @staticmethod
    def _restore_loop_settings(state: RunState) -> AgentLoopSettings:
        # Prefer the current structured settings payload; fall back to older runtime_config-only checkpoints.
        values = dict(state.loop_settings or {})
        if not values:
            values = {
                "max_iterations": state.runtime_config.get("max_iterations"),
                "max_tokens": state.runtime_config.get("max_tokens"),
                "max_tool_calls": state.runtime_config.get("max_tool_calls"),
                "compaction_trigger_tokens": state.runtime_config.get("compaction_trigger_tokens"),
                "compaction_target_tokens": state.runtime_config.get("compaction_target_tokens"),
            }
        if values.get("allowed_tools") is not None:
            values["allowed_tools"] = tuple(values["allowed_tools"])
        return AgentLoopSettings(**{key: value for key, value in values.items() if value is not None})

    @staticmethod
    def _restore_runtime(state: RunState) -> AgentRuntimeType | str | ActorRuntime:
        # Rebuild actor runtime config when checkpointed; linear and MCTS can use the enum value directly.
        runtime_type = AgentRuntimeType(state.runtime_type)
        if runtime_type in (
            AgentRuntimeType.ACTOR_MODEL,
            AgentRuntimeType.ACTOR_MODEL_P2P,
            AgentRuntimeType.ACTOR_MODEL_BROADCAST,
        ):
            return ActorRuntime(
                topology=runtime_type,
                dynamic_actors=bool(state.runtime_config.get("dynamic_actors", False)),
                max_loop=int(state.runtime_config.get("max_loop", 20)),
                termination_mode=str(state.runtime_config.get("termination_mode", "coordinator")),
                worker_model=state.runtime_config.get("worker_model"),
            )
        return runtime_type

    def _export_agent_metadata(self) -> dict[str, str]:
        # Render the agent-as-tool metadata into a plain dict.
        return {
            "name": self.agent_metadata.name,
            "description": self.agent_metadata.description,
            "use_cases": self.agent_metadata.use_cases,
        }

    @staticmethod
    def _record_resume_tool_mismatch(child: BaseAgent, expected: Sequence[str]) -> None:
        # Record a non-fatal marker when restored tools differ from the persisted set.
        got = tuple(child._tool_name(tool) for tool in child._agent_tool_items)
        if set(expected) != set(got):
            child.metadata["__resume_tool_mismatch__"] = {"expected": list(expected), "got": list(got)}

    async def receive(self, message: AgentMessage) -> None:
        self.history.append(message)

    async def generate_reply(
        self,
        message: str | AgentInput,
        *,
        context: BaseContext | None = None,
        history: Sequence[AgentMessage] = (),
        recipient: str = "orchestrator",
        **options: Any,
    ) -> AgentMessage:
        await self._ensure_mcp_connected()
        trace_ctx = None
        try:
            trace_metadata = dict(options.pop("trace_metadata", {}) or {})
            prompt, input_metadata = self._normalize_input(message)
            input_context_items, input_context_manager = self._normalize_input_context(message)
            self._active_prompt = prompt
            self._usage_tracker.reset()
            self._behavior_view = None
            runner, runner_type = self._runner_for_model()
            trace_ctx = self._tracer.start_trace(
                "agent.run",
                agent_name=self.name,
                run_id=self.runner_config.run_id,
                strategy="direct",
                prompt=self._safe_trace_value(prompt),
                system_prompt=self._safe_trace_value(self.system_prompt),
                tools=self._safe_trace_value(self._trace_tool_specs()),
                provider=self._runner_provider(runner),
                model=self._runner_model_name(runner),
                metadata=self._safe_trace_value({**self.metadata, **dict(input_metadata), **trace_metadata}),
            )
            agent_context = self._build_context(
                prompt,
                context=context,
                history=history,
                input_metadata=input_metadata,
                agentic_loop=True,
                input_context_items=input_context_items,
                input_context_manager=input_context_manager,
            )
            result = await self._run_direct(
                prompt,
                agent_context,
                runner=runner,
                runner_type=runner_type,
                trace_context=trace_ctx,
                runtime_metadata={**self.metadata, **dict(input_metadata), **trace_metadata},
                **options,
            )
            self._record_agent_stop(trace_ctx, result)
            if trace_ctx is not None:
                self._tracer.end_trace(trace_ctx, output=_format_trace_output(result))
        except Exception as exc:
            if trace_ctx is not None:
                self._tracer.end_trace(trace_ctx, error=exc)
            self._active_prompt = ""
            raise AgentExecutionError(
                f"Agent '{self.name}' failed to generate a reply.",
                details={"agent": self.name, "error_type": type(exc).__name__},
            ) from exc
        except BaseException as exc:
            # Catches CancelledError and other BaseException subclasses that bypass
            # the Exception handler, ensuring the root trace is always finalized.
            if trace_ctx is not None:
                self._tracer.end_trace(trace_ctx, error=exc)
            self._active_prompt = ""
            raise
        self._active_prompt = ""
        metadata: dict[str, Any] = {
            "strategy": result.strategy_name,
            "runner_type": runner_type,
            "provider": self.runner_config.provider,
            "model_name": self.runner_config.model_name,
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
            structured=result.structured,
        )
        self.history.append(reply)
        self.last_prompt = prompt
        self.last_reply = reply
        if self._trace_option is not None and self._trace_option.enabled:
            trace_artifact = metadata.get("trace")
            self.last_trace = dict(trace_artifact) if isinstance(trace_artifact, Mapping) else None
        if self._handoff_spec is not None:
            await self._run_auto_handoff(metadata)
        self._notify_session(reply)
        if self._queued_prompts and not self._draining_queued_prompts:
            await self._drain_queued_prompts(metadata)
        self._assert_schema_satisfied(result)
        return reply

    def _assert_schema_satisfied(self, result: AgentResult) -> None:
        # Fails loudly when a declared schema produced no instance, rather than returning a silent None.
        # @intent raise-after-the-turn-is-recorded
        # The failed attempt is still appended to history and checkpointed before this runs, so a
        # session keeps the evidence of what the model actually said instead of losing the turn.
        if self.output_schema is None or result.structured is not None:
            return
        raise OutputSchemaViolationError(
            f"Agent '{self.name}' declared an output_schema but produced no valid instance.",
            raw_output=result.output,
            validation_error=self._schema_violation_detail(result),
            stop_reason=str(result.metadata.get("stop_reason") or ""),
        )

    @staticmethod
    def _schema_violation_detail(result: AgentResult) -> str | None:
        # Pulls the schema contract's own error text out of the run's contract evaluations.
        evaluations = result.metadata.get("contract_evaluations")
        if not isinstance(evaluations, Sequence):
            return None
        for row in evaluations:
            if isinstance(row, Mapping) and row.get("name") == "SchemaConformance":
                return str(row.get("error") or "") or None
        return None

    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        """Async ergonomic alias for generate_reply()."""
        return await self.generate_reply(message, **options)

    async def pause(self, seconds: int) -> None:
        # Cooperatively yield for a validated whole-number delay without blocking other agent tasks.
        duration = PauseDuration(seconds=seconds)
        await asyncio.sleep(duration.seconds)

    def run(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        """Run the agent from synchronous code."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.generate_reply(message, **options))
        raise AgentExecutionError("BaseAgent.run() cannot be called from an active event loop; use await arun().")

    def get_usage(self) -> UsageRollup:
        """Return the live or final token-usage rollup for the current or most recent run."""
        return self._usage_tracker.rollup()

    def get_cost_usd(self) -> float | None:
        """Return total known USD cost for the current or most recent run, or None."""
        return self.get_usage().cost_usd

    async def arun_sequentially(self, prompts: Sequence[str | AgentInput], **options: Any) -> list[AgentMessage]:
        # Runs each prompt through generate_reply in order, preserving self.history across all calls.
        results: list[AgentMessage] = []
        for prompt in prompts:
            reply = await self.generate_reply(prompt, **options)
            results.append(reply)
        return results

    def run_sequentially(self, prompts: Sequence[str | AgentInput], **options: Any) -> list[AgentMessage]:
        # Synchronous entry point for sequential prompt execution; mirrors run()'s event-loop guard.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun_sequentially(prompts, **options))
        raise AgentExecutionError("BaseAgent.run_sequentially() cannot be called from an active event loop; use await arun_sequentially().")

    def enqueue_prompts(self, prompts: Sequence[str]) -> int:
        """Append prompts to the pending sequential-run queue and return the queue length."""
        if isinstance(prompts, str):
            raise ValueError("'prompts' must be a JSON array of strings, not a single string.")
        if not isinstance(prompts, (list, tuple)) or not prompts:
            raise ValueError("run_prompts_sequentially requires a non-empty 'prompts' array of strings.")
        max_queued_prompts = self.agent_loop_settings.max_queued_prompts
        if len(self._queued_prompts) + len(prompts) > max_queued_prompts:
            raise ValueError(
                f"Too many queued prompts: {len(self._queued_prompts) + len(prompts)} exceeds the limit of {max_queued_prompts}."
            )
        cleaned: list[str] = []
        for index, prompt in enumerate(prompts):
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"Prompt at index {index} must be a non-empty string.")
            cleaned.append(prompt.strip())
        self._queued_prompts.extend(cleaned)
        return len(self._queued_prompts)

    async def _drain_queued_prompts(self, metadata: dict[str, Any]) -> None:
        """Run queued prompts in order after the primary run, recording outcomes into metadata."""
        self._draining_queued_prompts = True
        self.last_queued_replies = []
        completed = 0
        try:
            # Pop-one loop so prompts queued by drained runs join the same bounded drain.
            while self._queued_prompts and completed < self.agent_loop_settings.max_queued_prompts:
                prompt = self._queued_prompts.pop(0)
                reply = await self.generate_reply(prompt)
                self.last_queued_replies.append(reply)
                completed += 1
            if self._queued_prompts:
                metadata["queued_prompts_truncated"] = len(self._queued_prompts)
                self._queued_prompts.clear()
        except Exception as exc:
            # A drained-run failure must not fail the already-successful primary reply.
            metadata["queued_prompt_error"] = repr(exc)
            self._queued_prompts.clear()
        finally:
            self._draining_queued_prompts = False
            if completed:
                metadata["queued_prompt_runs"] = completed

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
            agentic_loop=agentic_loop,
            context_items=self._merged_context_items(input_context_items),
            context_manager=self._merged_context_manager(input_context_manager),
        )

    async def _run_direct(
        self,
        message: str,
        context: BaseAgentContext,
        *,
        runner: object | None = None,
        runner_type: str = RUNNER_TYPE_TEXT,
        trace_context: object | None = None,
        runtime_metadata: Mapping[str, Any] | None = None,
        **options: Any,
    ) -> AgentResult:
        if runner is None:
            raise AgentExecutionError("Agent requires a runner.")
        if runner_type != RUNNER_TYPE_TEXT:
            return await self._run_non_text_runner(runner, message, context=context, **options)
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

    async def _run_non_text_runner(self, runner: object, message: str, *, context: BaseAgentContext, **options: Any) -> AgentResult:
        # Runs image/audio/video/embedding runners, walking the fallback chain on provider-level failures.
        from vidbyte.lib.errors import AllModelsFailedError

        index = 0
        attempts: list[dict[str, str]] = []
        errors: list[BaseException] = []
        active = runner
        while True:
            try:
                raw_result = await self._call_runner_once(active, message, context=context, **options)
            except BaseException as exc:
                if self.fallback is None or not self.fallback.is_model_error(exc):
                    raise
                next_index = self.fallback.advance(exc, index)
                if next_index is None:
                    if not attempts:
                        raise
                    raise AllModelsFailedError(
                        f"Agent '{self.name}' exhausted its fallback chain after {len(attempts)} model switch(es).",
                        attempts=attempts,
                        errors=[*errors, exc],
                    ) from errors[0]
                errors.append(exc)
                attempts.append(self.fallback.attempt_record(index, next_index, exc))
                active = self.fallback.build_runner(next_index)
                index = next_index
                continue
            metadata = dict(self._runner_output_metadata(raw_result))
            if attempts:
                metadata["fallback"] = self.fallback.result_metadata(attempts, context_reset=False)
            return AgentResult(
                output=self._runner_output_text(raw_result),
                strategy_name="direct_runner",
                metadata=metadata,
            )

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

        if self.runtime_type is AgentRuntimeType.LINEAR:
            kwargs["output_contract"] = self._output_contract_with_schema()
            kwargs["usage_tracker"] = self._usage_tracker
            kwargs["fallback"] = self.fallback

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
        # Appends settings-driven and tracing middleware to the user middleware.
        middleware = self.middleware
        if self.agent_loop_settings.tool_error_policy is not None:
            from vidbyte.middleware.builtins import ToolErrorPolicyMiddleware
            middleware = (*middleware, ToolErrorPolicyMiddleware(self.agent_loop_settings.tool_error_policy))
        if self._trace_option is None or not self._trace_option.enabled:
            return middleware
        from vidbyte.middleware.continual_trace import ContinualTraceMiddleware
        return (*middleware, ContinualTraceMiddleware(self._trace_option, source_agent=self))

    def _output_contract_with_schema(self) -> "AgentLoopSettingsOutputContract":
        # Adds the declared schema to this run's contracts so a malformed answer is repaired in-loop.
        # Read here rather than at construction so assigning output_schema after build still applies.
        contract = self.agent_loop_settings.output_contract
        if self.output_schema is None:
            return contract
        from vidbyte.agents.contracts import SchemaConformance

        return contract.with_contract(SchemaConformance(self.output_schema))

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
    ) -> tuple[str, Mapping[str, Any]]:
        if isinstance(message, AgentInput):
            return message.prompt, message.metadata
        return message, {}

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

    def _runner_for_model(self) -> tuple[object, str]:
        # Resolve and cache the executable runner for this agent's provider/model identity.
        # timeout_seconds is omitted when unset so the model config keeps its own default.
        options = {"timeout_seconds": self.runner_config.timeout_seconds} if self.runner_config.timeout_seconds is not None else {}
        utility = Runner.from_model(
            provider=self.runner_config.provider,
            model_name=self.runner_config.model_name,
            api_key=self.runner_config.api_key,
            temperature=self.runner_config.temperature,
            options=options,
        )
        runner_type = utility.resolve_runner_type()
        if runner_type not in self._runner_cache:
            self._runner_cache[runner_type] = utility.build()
        return self._runner_cache[runner_type], runner_type

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

    def _trace_tool_specs(self) -> list[dict[str, Any]]:
        """Build a list of full tool specs (name, description, parameters) for tracing."""
        try:
            builtin_specs = self.tools.specs()
        except Exception:
            builtin_specs = ()
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for spec in builtin_specs:
            name = getattr(spec, "name", None)
            if name and name not in seen:
                seen.add(name)
                result.append(self._tool_spec_to_dict(spec))
        for tool in self._agent_tool_items:
            name = self._tool_name(tool)
            if name in seen:
                continue
            seen.add(name)
            spec_attr = getattr(tool, "spec", None)
            if spec_attr is not None:
                try:
                    real_spec = spec_attr() if callable(spec_attr) else spec_attr
                    result.append(self._tool_spec_to_dict(real_spec))
                    continue
                except Exception:
                    pass
            result.append({"name": name})
        return result

    def _record_agent_stop(self, parent: object | None, result: AgentResult) -> None:
        # Records a semantic agent stop span when using TraceController-backed tracing.
        if not _is_semantic_tracer(self._tracer):
            return
        metadata = dict(result.metadata)
        span = self._tracer.start_span(
            "agent.stop",
            parent=parent,
            stop_reason=metadata.get("stop_reason"),
            strategy=result.strategy_name,
            iteration_count=metadata.get("iteration_count"),
            tokens_used=metadata.get("tokens_used"),
            tool_call_count=metadata.get("tool_call_count"),
        )
        self._tracer.end_span(span, output=str(result.output))

    @staticmethod
    def _tool_spec_to_dict(spec: object) -> dict[str, Any]:
        """Convert a ToolSpec-like object to a dict safe for trace backends."""
        entry: dict[str, Any] = {}
        entry["name"] = getattr(spec, "name", "")
        entry["description"] = getattr(spec, "description", "")
        params = getattr(spec, "parameters", ())
        if params:
            entry["parameters"] = [
                {"name": getattr(p, "name", ""), "type": getattr(p, "type", ""),
                 "description": getattr(p, "description", ""), "required": getattr(p, "required", False)}
                for p in params
            ]
        return entry


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


def _format_trace_output(result: Any) -> str:
    """Format agent.run output for tracing: wraps each agentic loop iteration in XML tags.

    When iteration_outputs are present in result metadata, produces:
        <iteration_1>...<iteration_1>
        <iteration_2>...<iteration_2>
        ...
    This makes the full agentic loop visible in LangSmith instead of only the final output.
    Falls back to result.output when no iteration data is available (e.g. single-shot agents).
    """
    iteration_outputs = None
    metadata = getattr(result, "metadata", None)
    if isinstance(metadata, Mapping):
        iteration_outputs = metadata.get("iteration_outputs")
    if not iteration_outputs:
        return str(getattr(result, "output", result) or "")
    return "\n".join(
        f"<iteration_{i + 1}>\n{out}\n</iteration_{i + 1}>"
        for i, out in enumerate(iteration_outputs)
    )


def _is_semantic_tracer(tracer: TracerBase) -> bool:
    # Detects TraceController-like tracers without importing vidbyte.trace during agent initialization.
    return all(hasattr(tracer, attr) for attr in ("inner", "profile", "translator"))
