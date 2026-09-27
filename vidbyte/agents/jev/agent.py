"""FILE: vidbyte/agents/jev/agent.py

PURPOSE: Exposes `Jev`, the coordinator that selects one configured JevAgent profile and temporarily applies its execution settings to the main BaseAgent run.
ROLE IN CODEBASE: Callers construct `Jev` with `JevAgentSettings`; it owns the preflight gate, profile router, response writer, run lock, and the runtime handoff to `JevRuntime`.
ARCHITECTURE NOTE: Profile selection happens before BaseAgent resolves its runner, while preflight remains first. A snapshot restores main-agent configuration after every run; the candidate's history, trackers, session, MCP handles, and tracer are not adopted.
FUNCTION INVENTORY: `Jev(settings, runtime_settings)` initializes the coordinator; `generate_reply(message, ...)` gates, selects, applies, runs, and restores; `_snapshot_configuration()` and `_restore_configuration(snapshot)` own the temporary settings boundary; `_runtime_extension_kwargs()` supplies run-local runtime inputs.
COMMON MODIFICATION PATTERNS: Add transferable profile config to `_JevConfiguration`, both apply/restore helpers, and the restoration tests; keep question semantics in prompt assets and routing policy in `JevAgentRouter`.
WHAT NOT TO DO IN THIS FILE: 1. Do not put TypeSafe wire encoding here; `vidbyte/providers/typesafe.py` owns it. 2. Do not run a selected profile as a child; its settings are applied to this coordinator. 3. Do not move selection into `JevRuntime`; BaseAgent resolves the runner before runtime entry.
KNOWN EDGE CASES: The clarity writer uses the first profile before selection; per-instance calls serialize; cancellation and all execution exceptions restore temporary settings; profile MCP servers are connected for the run and closed before restoration.
RELATED DOCS: `docs/design/jev-agent-profile-routing.md`, `skills/jev-agent/SKILL.md`, and `skills/asking-jev-questions/SKILL.md`.
TESTS: `tests/test_jev_agent.py`, `tests/test_jev_preflight.py`, `tests/test_jev_tool_selector.py`, and `scripts/test-jev-agent-profile-routing.py`.
CONCURRENCY MODEL: One per-instance `asyncio.Semaphore(1)` serializes runs because BaseAgent owns mutable history, usage, tools, and trace state; independent Jev instances run independently.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings
from vidbyte.agents.jev.specialists import JevAgentRoute, JevAgentRouter
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.context.handoff import Handoff
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.context.window import ContextWindowAlgorithm
from vidbyte.lib.dataclasses.agents import (
    AgentForkSettings,
    AgentMetadata,
    AgentRunnerConfig,
    AgentRuntimeConfig,
)
from vidbyte.lib.dataclasses.context import BaseContext
from vidbyte.lib.dataclasses.jev import JevAgent, JevAgentResponse, JevAgentSelection
from vidbyte.lib.dataclasses.trace import TraceOption
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.middleware import AgentMiddleware
from vidbyte.tools.security import PermissionPolicy


@dataclass(frozen=True, slots=True)
class _JevConfiguration:
    """Snapshot of only the coordinator settings that a selected profile temporarily replaces."""

    name: str
    system_prompt: str
    runner_config: AgentRunnerConfig
    fallback_spec: Any
    fallback: Any
    runner_cache: dict[str, object]
    agent_tool_items: tuple[object, ...]
    tools: Any
    permission_policy: PermissionPolicy
    agent_loop_settings: AgentLoopSettings
    max_tool_rounds: int | None
    runtime_config: AgentRuntimeConfig
    middleware: tuple[AgentMiddleware, ...]
    description: str
    capabilities: tuple[str, ...]
    agent_metadata: AgentMetadata
    context_items: tuple[ContextItem, ...]
    context_manager: ContextManager | None
    algorithm: ContextWindowAlgorithm
    metadata: dict[str, Any]
    output_schema: Any
    handoff_spec: Handoff | None
    trace_option: TraceOption | None
    mcp_handles: list[Any]
    pending_mcp_configs: list[Any]


class Jev(BaseAgent):
    """Opinionated profile-selecting coordinator with the established BaseAgent execution loop."""

    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings | None = None) -> None:
        # @intent first-profile-seeds-coordinator
        # `JevAgentSettings` intentionally contains only profiles, so the first profile supplies a complete
        # BaseAgent initialization surface before a request is routed. This seed is not a fallback policy:
        # multi-profile runs replace it temporarily with the selected profile before runner construction.
        # Seeds BaseAgent from the first profile while retaining Jev as the main run owner.
        if not isinstance(settings, JevAgentSettings):
            raise ConfigurationError("Jev requires a JevAgentSettings instance.")
        resolved_runtime_settings = runtime_settings or JevRuntimeSettings()
        if not isinstance(resolved_runtime_settings, JevRuntimeSettings):
            raise ConfigurationError("Jev runtime_settings must be a JevRuntimeSettings instance.")
        bootstrap_profile = settings.agents[0]
        bootstrap = self._fork_profile(bootstrap_profile)
        self.settings = settings
        self.runtime_settings = resolved_runtime_settings
        self._response = JevResponse()
        self._profile_semaphore = asyncio.Semaphore(1)
        self._prepared_preflight_passed: bool | None = None
        self._prepared_route: JevAgentRoute | None = None
        self._configuration_snapshot: _JevConfiguration | None = None
        self.preflight = JevPreflightGate(resolved_runtime_settings, self._response, bootstrap_profile.agent)
        self.router = JevAgentRouter(settings, resolved_runtime_settings.decision)
        super().__init__(
            name=bootstrap_profile.title,
            system_prompt=bootstrap.system_prompt,
            runtime=AgentRuntimeType.JEV,
            tools=bootstrap._agent_tool_items,
            permission_policy=bootstrap.permission_policy,
            agent_loop_settings=bootstrap.agent_loop_settings,
            api_key=bootstrap.runner_config.api_key,
            provider=bootstrap.runner_config.provider,
            model_name=bootstrap.runner_config.model_name,
            temperature=bootstrap.runner_config.temperature,
            timeout_seconds=bootstrap_profile.agent.runner_config.timeout_seconds,
            run_id=bootstrap_profile.agent.runner_config.run_id,
            middleware=bootstrap.middleware,
            description=bootstrap.description,
            capabilities=bootstrap.capabilities,
            agent_metadata=bootstrap.agent_metadata,
            context_items=bootstrap.context_items,
            context_manager=self._copy_context_manager(bootstrap.context_manager),
            algorithm=bootstrap.algorithm,
            metadata=bootstrap_profile.agent.metadata,
            tracer=bootstrap._tracer,
            output_schema=bootstrap.output_schema,
            handoff=bootstrap._handoff_spec,
            trace_option=bootstrap._trace_option,
            fallback=bootstrap._fallback_spec,
        )
        self._runner_cache = dict(bootstrap._runner_cache)
        self._pending_mcp_configs = list(bootstrap._pending_mcp_configs)

    @property
    def response(self) -> JevAgentResponse:
        # Returns the structured decisions and generated output for the latest coordinator run.
        return self._response.state

    async def generate_reply(self, message: str | AgentInput, *, context: BaseContext | None = None, history: Sequence[AgentMessage] = (), recipient: str = "orchestrator", **options: Any) -> AgentMessage:
        # @intent preflight-before-profile-selection
        # Clarity checks are a gate on starting any profile work, not a signal that should be spent after
        # the router has already chosen a model. Keep this order so unclear requests make no routing call.
        # The per-instance lock is load-bearing because BaseAgent history, trackers, tools, and the selected
        # model configuration are mutable shared state; overlapping runs could otherwise mix two profiles.
        # Preserves preflight-before-routing order and confines selected settings to one serialized run.
        async with self._profile_semaphore:
            request, _ = self._normalize_input(message)
            self._response.start(request)
            self._usage_tracker.reset()
            try:
                return await super().generate_reply(message, context=context, history=history, recipient=recipient, **options)
            finally:
                await self._restore_prepared_configuration()

    async def _prepare_run(self, message: str | AgentInput) -> None:
        # Runs gate and profile selection after tracker reset but before MCP, runner, and context setup.
        request, _ = self._normalize_input(message)
        self._prepared_preflight_passed = await self.preflight.pass_(request)
        if not self._prepared_preflight_passed:
            return
        route = await self._select_profile(request)
        self._prepared_route = route
        if route is not None:
            self._response.selected(route.selection)
        profile = self._profile_for_selection(None if route is None else route.selection)
        snapshot = self._snapshot_configuration()
        self._configuration_snapshot = snapshot
        self._apply_profile_configuration(profile, snapshot)

    async def _restore_prepared_configuration(self) -> None:
        # Restores a profile after BaseAgent exits and then accounts for the earlier TypeSafe decision call.
        snapshot = self._configuration_snapshot
        route = self._prepared_route
        try:
            if snapshot is not None:
                await self._restore_configuration(snapshot)
        finally:
            self._record_routing_usage(route)
            self._configuration_snapshot = None
            self._prepared_route = None
            self._prepared_preflight_passed = None

    async def _select_profile(self, request: str) -> JevAgentRoute | None:
        # Skips TypeSafe for one profile and otherwise asks the configured router for its maximum-probability choice.
        if len(self.settings.agents) == 1:
            return None
        return await self.router.select(request)

    def _record_routing_usage(self, route: JevAgentRoute | None) -> None:
        # @intent routing-usage-is-agent-owned
        # BaseAgent resets its tracker before the generative loop, while Jev's decision happens before that
        # reset so the selected model can be applied in time. Record the raw TypeSafe response afterward,
        # once, so callers see both model calls without duplicate billing or lost decision usage.
        if route is not None:
            self._usage_tracker.record_call(route.decision_response)

    def _profile_for_selection(self, selection: JevAgentSelection | None) -> JevAgent:
        # Resolves the route result to its already validated profile, defaulting to the sole candidate.
        title = self.settings.agents[0].title if selection is None else selection.title
        return next(agent for agent in self.settings.agents if agent.title == title)

    def _snapshot_configuration(self) -> _JevConfiguration:
        # @intent restore-all-profile-overlays
        # BaseAgent has mutable model, tools, permission, context, and fallback configuration. Capture the
        # complete supported surface before replacing it; omitting one field can leak the previous role into
        # later requests even though the visible prompt and provider appear restored.
        # Captures the main agent's current configurable execution state before profile application.
        return _JevConfiguration(
            name=self.name,
            system_prompt=self.system_prompt,
            runner_config=self.runner_config,
            fallback_spec=self._fallback_spec,
            fallback=self.fallback,
            runner_cache=self._runner_cache,
            agent_tool_items=self._agent_tool_items,
            tools=self.tools,
            permission_policy=self.permission_policy,
            agent_loop_settings=self.agent_loop_settings,
            max_tool_rounds=self.max_tool_rounds,
            runtime_config=self.runtime_config,
            middleware=self.middleware,
            description=self.description,
            capabilities=self.capabilities,
            agent_metadata=self.agent_metadata,
            context_items=self.context_items,
            context_manager=self.context_manager,
            algorithm=self.algorithm,
            metadata=self.metadata,
            output_schema=self.output_schema,
            handoff_spec=self._handoff_spec,
            trace_option=self._trace_option,
            mcp_handles=self._mcp_handles,
            pending_mcp_configs=self._pending_mcp_configs,
        )

    def _apply_profile_configuration(self, profile: JevAgent, snapshot: _JevConfiguration) -> None:
        # @intent per-run-profile-settings
        # The winning profile changes the prompt, model, tool catalog, permissions, and loop policy for this
        # main-agent turn only. A later call must begin with the coordinator's original configuration, even
        # after a model failure, cancellation, or MCP cleanup; the enclosing finally owns that restoration.
        # Applies a fresh copy of the profile's reusable configuration, retaining coordinator-owned identity and state.
        self._mcp_handles = []
        self._pending_mcp_configs = []
        self._runner_cache = {}
        template = self._fork_profile(profile)
        self._apply_profile_identity(profile, template, snapshot)
        self._apply_profile_tools(template)
        self._apply_profile_policy(template)
        self._apply_profile_context(profile, template)
        self._apply_profile_mcp(template)

    def _apply_profile_identity(self, profile: JevAgent, template: BaseAgent, snapshot: _JevConfiguration) -> None:
        # @intent profile-model-identity
        # Provider, model, API key, timeout, fallback, and identity must move together. A model cache from
        # another profile can call the wrong provider even when the selected model name looks correct.
        # Replaces the run-facing prompt/model identity while preserving Jev's root run id.
        self.name = profile.title
        self.system_prompt = template.system_prompt
        self.runner_config = replace(template.runner_config, run_id=snapshot.runner_config.run_id, timeout_seconds=profile.agent.runner_config.timeout_seconds)
        self._fallback_spec = template._fallback_spec
        self.fallback = template.fallback
        self._runner_cache = dict(template._runner_cache)
        self.description = template.description
        self.capabilities = tuple(template.capabilities)
        self.agent_metadata = template.agent_metadata
        self.metadata = dict(profile.agent.metadata)

    def _apply_profile_tools(self, template: BaseAgent) -> None:
        # Installs isolated tool copies and rebinds agent-aware tools to the main coordinator.
        self._agent_tool_items = tuple(template._agent_tool_items)
        setattr(self, "tools", self._catalog_from_agent_tools(self._agent_tool_items))
        for item in self._agent_tool_items:
            self._bind_agent_tool_context(item)

    def _apply_profile_policy(self, template: BaseAgent) -> None:
        # @intent selected-profile-permissions
        # The selected profile's tools are safe only with its matching permission policy and loop controls.
        # Copy both before execution; combining one profile's tools with another's grants can expose actions
        # the selected role was not configured to perform.
        # Loads tool authorization, loop budgets, middleware, and output policy from the selected profile.
        self.permission_policy = template.permission_policy
        self.agent_loop_settings = template.agent_loop_settings
        self.max_tool_rounds = template.max_tool_rounds
        self.runtime_config = template.runtime_config
        self.middleware = tuple(template.middleware)
        self.output_schema = template.output_schema
        self._handoff_spec = template._handoff_spec
        self._trace_option = template._trace_option

    def _apply_profile_context(self, profile: JevAgent, template: BaseAgent) -> None:
        # Uses copied context data so one candidate cannot mutate its configured template during a run.
        self.context_items = tuple(template.context_items)
        self.context_manager = self._copy_context_manager(profile.agent.context_manager)
        self.algorithm = template.algorithm

    def _apply_profile_mcp(self, template: BaseAgent) -> None:
        # @intent profile-mcp-lifecycle
        # Replay configuration rather than copying live MCP handles: handles own subprocesses and bridged
        # tools that cannot safely be shared across profiles or runs. The matching cleanup closes only the
        # temporary profile handles before Jev's original connections are restored.
        # Replays configured MCP connections for this profile without sharing live handles across runs.
        self._mcp_handles = []
        self._pending_mcp_configs = list(template._pending_mcp_configs)

    async def _restore_configuration(self, snapshot: _JevConfiguration) -> None:
        # @intent restore-coordinator-after-profile-run
        # The profile's settings are only a per-request configuration overlay. If a run exits through model
        # failure, cancellation, output validation, or MCP cleanup, the next caller must still observe the
        # same Jev coordinator configuration it had before the selected profile started.
        await self.close_mcp_servers()
        self._restore_identity(snapshot)
        self._restore_execution(snapshot)
        self._restore_tools(snapshot)
        self._restore_context(snapshot)
        self._restore_mcp(snapshot)

    def _restore_identity(self, snapshot: _JevConfiguration) -> None:
        # @intent restore-profile-model-and-fallback
        # A selected provider or fallback must never become the coordinator's implicit configuration for
        # the next user request; restore the exact saved object rather than reconstructing it from defaults.
        # Restores the coordinator name, prompt, model identity, and fallback configuration.
        self.name = snapshot.name
        self.system_prompt = snapshot.system_prompt
        self.runner_config = snapshot.runner_config
        self._fallback_spec = snapshot.fallback_spec
        self.fallback = snapshot.fallback
        self._runner_cache = snapshot.runner_cache

    def _restore_tools(self, snapshot: _JevConfiguration) -> None:
        # @intent restore-profile-tool-permissions
        # Tool visibility and authorization form one boundary. Restoring only the catalog or only permissions
        # could leave a later request with a mismatched capability/security pair.
        # Restores the coordinator's catalog and permission boundary after temporary profile execution.
        self._agent_tool_items = snapshot.agent_tool_items
        setattr(self, "tools", cast(Any, snapshot.tools))
        self.permission_policy = snapshot.permission_policy

    def _restore_execution(self, snapshot: _JevConfiguration) -> None:
        # Restores the coordinator's loop, middleware, and agent-facing output settings.
        self.agent_loop_settings = snapshot.agent_loop_settings
        self.max_tool_rounds = snapshot.max_tool_rounds
        self.runtime_config = snapshot.runtime_config
        self.middleware = snapshot.middleware
        self.description = snapshot.description
        self.capabilities = snapshot.capabilities
        self.agent_metadata = snapshot.agent_metadata
        self.output_schema = snapshot.output_schema
        self._handoff_spec = snapshot.handoff_spec
        self._trace_option = snapshot.trace_option

    def _restore_context(self, snapshot: _JevConfiguration) -> None:
        # Restores context and algorithm objects owned by the coordinator.
        self.context_items = snapshot.context_items
        self.context_manager = snapshot.context_manager
        self.algorithm = snapshot.algorithm
        self.metadata = snapshot.metadata

    def _restore_mcp(self, snapshot: _JevConfiguration) -> None:
        # @intent restore-coordinator-mcp-handles
        # Jev's original live server handles remain open but detached during a selected profile run; reattach
        # those exact handles only after the profile-owned handles have been closed.
        # Reattaches the coordinator's original live MCP handles and pending configuration references.
        self._mcp_handles = snapshot.mcp_handles
        self._pending_mcp_configs = snapshot.pending_mcp_configs

    @staticmethod
    def _fork_profile(profile: JevAgent) -> BaseAgent:
        # Clones reusable settings, bound tools, and replayable MCP configs without importing the candidate's run history.
        return profile.agent.fork(AgentForkSettings(name=profile.title, include_history=False, include_run_state=False, run_id=profile.agent.runner_config.run_id))

    @staticmethod
    def _copy_context_manager(manager: ContextManager | None) -> ContextManager | None:
        # Prevents profile execution from changing the configured template's mutable context manager.
        return None if manager is None else ContextManager(manager.items())

    @property
    def _current_preflight_passed(self) -> bool:
        # Fails closed if a generic BaseAgent reaches the private JEV runtime outside Jev.generate_reply().
        return self._prepared_preflight_passed is True

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Supplies the validated runtime policy and one run's already-computed gate result.
        return {"runtime_settings": self.runtime_settings, "response": self._response, "preflight_passed": self._current_preflight_passed}


__all__ = ["Jev"]
