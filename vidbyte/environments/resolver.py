"""Context Protocol Header

Description:
    Defines HarnessSpecResolver, the single place where a validated HarnessSpec
    becomes a live BaseAgent bound to an environment session.
Purpose:
    Keeps name-to-object resolution out of specs and environments so harness
    configuration stays declarative while construction reuses existing SDK
    constructors, registries, and the environment tool-authority rule.
Architecture:
    - HarnessSpecResolver: Per-environment builder composing runtime, loop
      settings, context algorithm, primitives, middleware, tools, and tracing.
Relations:
    Consumes vidbyte.environments.spec tables; produces BaseAgents for
    vidbyte.environments.runner.
Similar Files:
    - vidbyte/agents/base.py: BaseAgent constructor this resolver targets.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.runtimes.configs import ActorRuntime, LinearRuntime, MctsSearchRuntime
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context.algorithms import ContextWindowAlgorithm, ToolResultAdmission
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.environments.spec import (
    ALGORITHM_SETTINGS_OWNERS,
    CONTEXT_MANAGER_TOOL_NAMES,
    FILESYSTEM_TOOL_TABLE,
    PASSTHROUGH_ALGORITHM_PRESETS,
    PRIMITIVE_TABLE,
    MIDDLEWARE_TABLE,
    TOOL_TABLE,
    HarnessSpec,
)
from vidbyte.environments.types import EnvSession
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.lib.dataclasses.trace import TraceOption
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.middleware import AgentMiddleware
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.catalog import Tools
from vidbyte.trace.continual.prebuilt import ActionTraceModel
from vidbyte.trace.debug import DebugTracer

if TYPE_CHECKING:
    from vidbyte.environments.base import Environment
    from vidbyte.lib.tracing import TracerBase

# Tools whose constructors take a required root_dir that defaults to the session workspace.
_ROOT_DIR_TOOL_NAMES: frozenset[str] = frozenset({"glob", "grep", "semantic_search", "patch_file"})

# Admission defaults for presets that carry no settings-bearing algorithm dataclass.
_PASSTHROUGH_ADMISSION: dict[str, ToolResultAdmission] = {
    "default": ToolResultAdmission.RAW,
    "raw_tool_outputs": ToolResultAdmission.RAW,
    "compact_tool_outputs": ToolResultAdmission.COMPACT,
    "hide_tool_outputs": ToolResultAdmission.HIDE_RAW,
    "no_raw_tool_outputs": ToolResultAdmission.HIDE_RAW,
}


class HarnessSpecResolver:
    """Builds live BaseAgents from declarative HarnessSpecs bound to environment sessions."""

    def __init__(self, environment: "Environment") -> None:
        # Stores the environment whose authority rule filters every resolved tool surface.
        self._environment = environment

    def build_agent(self, spec: HarnessSpec, session: EnvSession) -> BaseAgent:
        """Resolve every spec axis and assemble the configured BaseAgent."""
        context_items, context_manager = self.resolve_context(spec)
        context_manager = self._ensure_manager_for_tools(spec, context_manager)
        tracer, trace_option = self.resolve_trace(spec)
        return BaseAgent(
            name=spec.name,
            system_prompt=self.resolve_system_prompt(spec),
            runtime=self.resolve_runtime(spec),
            tools=self.resolve_tools(spec, session, context_manager),
            agent_loop_settings=self.resolve_loop_settings(spec),
            middleware=self.resolve_middleware(spec),
            provider=spec.model.provider,
            model_name=spec.model.model,
            temperature=spec.model.temperature,
            context_items=context_items,
            context_manager=context_manager,
            algorithm=self.resolve_algorithm(spec),
            tracer=tracer,
            trace_option=trace_option,
            output_schema=spec.output_schema,
            metadata={"harness_spec": spec.model_dump()},
        )

    def resolve_system_prompt(self, spec: HarnessSpec) -> str:
        """Return the literal system prompt or load the referenced catalog prompt."""
        if spec.system_prompt is not None:
            return spec.system_prompt
        try:
            key = Prompt(spec.system_prompt_ref)
        except ValueError as exc:
            raise ConfigurationError(
                f"Unknown system_prompt_ref {spec.system_prompt_ref!r}; not a Vidbyte prompt catalog key."
            ) from exc
        return Prompts().get(key)

    def resolve_runtime(self, spec: HarnessSpec) -> LinearRuntime | MctsSearchRuntime | ActorRuntime:
        """Build the runtime configuration object for the spec's runtime kind."""
        if spec.runtime.kind == "linear":
            return LinearRuntime()
        if spec.runtime.kind == "mcts_search":
            return MctsSearchRuntime()
        return ActorRuntime(
            topology=spec.runtime.topology,
            dynamic_actors=spec.runtime.dynamic_actors,
            max_loop=spec.runtime.max_loop,
            termination_mode=spec.runtime.termination_mode,
            worker_model=spec.runtime.worker_model,
        )

    def resolve_loop_settings(self, spec: HarnessSpec) -> AgentLoopSettings:
        """Build AgentLoopSettings, which re-validates budgets authoritatively."""
        return AgentLoopSettings(**spec.loop.model_dump())

    def resolve_algorithm(self, spec: HarnessSpec) -> ContextWindowAlgorithm:
        """Build the ContextWindowAlgorithm for the preset with settings and admission overrides."""
        algorithm_spec = spec.context_algorithm
        kwargs: dict[str, Any] = {"name": algorithm_spec.preset}
        admission = _PASSTHROUGH_ADMISSION.get(algorithm_spec.preset, ToolResultAdmission.RAW)
        if algorithm_spec.tool_result_admission is not None:
            admission = ToolResultAdmission(algorithm_spec.tool_result_admission)
        kwargs["tool_result_admission"] = admission
        if algorithm_spec.max_tool_result_chars is not None:
            kwargs["max_tool_result_chars"] = algorithm_spec.max_tool_result_chars
        if algorithm_spec.preset not in PASSTHROUGH_ALGORITHM_PRESETS:
            owner = ALGORITHM_SETTINGS_OWNERS[algorithm_spec.preset]
            kwargs[algorithm_spec.preset] = owner(**self._coerce_algorithm_settings(algorithm_spec.settings))
        return ContextWindowAlgorithm(**kwargs)

    def resolve_context(self, spec: HarnessSpec) -> tuple[tuple[ContextItem, ...], ContextManager | None]:
        """Instantiate primitives, splitting unmanaged items from manager-registered ones."""
        unmanaged: list[ContextItem] = []
        manager: ContextManager | None = None
        for index, primitive_spec in enumerate(spec.context_primitives):
            fields = dict(primitive_spec.fields)
            if primitive_spec.managed:
                # Managed registry entries need an address; default one per spec position.
                fields.setdefault("primitive_id", f"{primitive_spec.kind}_{index}")
            item = self._build_primitive(index, primitive_spec.kind, fields)
            if not primitive_spec.managed:
                unmanaged.append(item)
                continue
            if manager is None:
                manager = ContextManager()
            manager.upsert(item, placement=ContextWindowPlacement(primitive_spec.placement))
        return tuple(unmanaged), manager

    def resolve_middleware(self, spec: HarnessSpec) -> tuple[AgentMiddleware, ...]:
        """Instantiate the middleware pipeline in spec order."""
        pipeline: list[AgentMiddleware] = []
        for index, entry in enumerate(spec.middleware):
            middleware_cls = MIDDLEWARE_TABLE[entry.name]
            try:
                pipeline.append(middleware_cls(**entry.settings))
            except TypeError as exc:
                raise ConfigurationError(f"middleware[{index}] '{entry.name}': {exc}") from exc
        return tuple(pipeline)

    def resolve_tools(self, spec: HarnessSpec, session: EnvSession, context_manager: ContextManager | None) -> Tools:
        """Build requested tools workspace-scoped by default, then apply environment authority."""
        requested: list[Any] = []
        for index, entry in enumerate(spec.tools):
            requested.append(self._build_tool(index, entry.name, dict(entry.settings), session, context_manager))
        return self._environment.tools(session, requested=Tools(requested) if requested else None)

    def resolve_trace(self, spec: HarnessSpec) -> tuple["TracerBase | type[TracerBase] | None", TraceOption | None]:
        """Build the tracer choice and the continual trace option when enabled."""
        tracer = DebugTracer if spec.trace.tracer == "debug" else None
        trace_option: TraceOption | None = None
        if spec.trace.continual:
            schema: Any = spec.trace.schema_fields if spec.trace.schema_fields else ActionTraceModel
            trace_option = TraceOption.continual(
                schema,
                every_n_iterations=spec.trace.every_n_iterations,
                max_trace_iterations=spec.trace.max_trace_iterations,
            )
        return tracer, trace_option

    def _ensure_manager_for_tools(self, spec: HarnessSpec, manager: ContextManager | None) -> ContextManager | None:
        # Creates a manager when a requested tool needs one and no managed primitive made it.
        needs_manager = any(entry.name in CONTEXT_MANAGER_TOOL_NAMES for entry in spec.tools)
        if needs_manager and manager is None:
            manager = ContextManager()
        return manager

    def _coerce_algorithm_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        # Converts JSON-level placement strings into the ContextWindowPlacement enum.
        coerced = dict(settings)
        if isinstance(coerced.get("placement"), str):
            coerced["placement"] = ContextWindowPlacement(coerced["placement"])
        return coerced

    def _build_primitive(self, index: int, kind: str, fields: dict[str, Any]) -> ContextItem:
        # Instantiates one context primitive, wrapping constructor errors with the spec path.
        primitive_cls = PRIMITIVE_TABLE[kind]
        try:
            return primitive_cls(**fields)
        except TypeError as exc:
            raise ConfigurationError(f"context_primitives[{index}] '{kind}': {exc}") from exc

    def _build_tool(self, index: int, name: str, settings: dict[str, Any], session: EnvSession, context_manager: ContextManager | None) -> Any:
        # Instantiates one requested tool with workspace-scoped defaults and manager injection.
        tool_cls = TOOL_TABLE[name]
        try:
            if name in FILESYSTEM_TOOL_TABLE:
                settings.setdefault("root", str(session.workspace_dir))
                return tool_cls(FileSystemToolConfig(**settings))
            if name in CONTEXT_MANAGER_TOOL_NAMES:
                if context_manager is None:
                    raise ConfigurationError(f"tools[{index}] '{name}' requires a ContextManager.")
                return tool_cls(context_manager, **settings)
            if name in _ROOT_DIR_TOOL_NAMES:
                settings.setdefault("root_dir", str(session.workspace_dir))
            return tool_cls(**settings)
        except TypeError as exc:
            raise ConfigurationError(f"tools[{index}] '{name}': {exc}") from exc


__all__ = [
    "HarnessSpecResolver",
]
