"""Context Protocol Header

Description:
    Exposes MultiAgent as the BaseAgent-compatible ledger-driven team facade.
Purpose:
    Presents a small public protocol while delegating validation, context, lifecycle,
    execution, tracing, cleanup, dispatch, ledger policy, and finalization.
Architecture:
    MultiAgent initializes class-based collaborators and owns only public facade state.
Relations:
    Exported through vidbyte.agents; delegates to sibling runtime modules and vidbyte.context.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.handoff import HandoffAgent
from vidbyte.agents.multi.cleanup import MultiAgentCleanup
from vidbyte.agents.multi.dispatcher import MultiAgentDispatcher
from vidbyte.agents.multi.ledger_controller import MultiAgentOrchestratorLedger
from vidbyte.agents.multi.lifecycle import MultiAgentLifecycle
from vidbyte.agents.multi.orchestrator import (
    MagenticOneOrchestrator,
    MultiAgentOrchestrator,
)
from vidbyte.agents.multi.orchestrator_runtime import MultiAgentOrchestratorRunner
from vidbyte.agents.multi.post_run import MultiAgentPostRunner
from vidbyte.agents.multi.pre_run import MultiAgentPreRunner
from vidbyte.agents.multi.runner import MultiAgentRunner
from vidbyte.agents.multi.tracing import MultiAgentTracer
from vidbyte.agents.multi.transfer import AgentBinding, AgentTransfer
from vidbyte.agents.multi.validation import MultiAgentValidator
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage
from vidbyte.context.handoff import Handoff
from vidbyte.context.multi_agent import MultiAgentContext
from vidbyte.lib.dataclasses.agents import AgentForkSettings, AgentMetadata
from vidbyte.lib.dataclasses.context import BaseContext
from vidbyte.lib.dataclasses.multi_agent import (
    CompletionCheck,
    LedgerFactory,
    MultiAgentEventCallback,
    MultiAgentResult,
    MultiAgentRunState,
    MultiAgentSettings,
    TaskLedgerSnapshot,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import TracerBase

if TYPE_CHECKING:
    from vidbyte.sessions.session import Session
    from vidbyte.sessions.store import SessionStore


class MultiAgent(BaseAgent):
    """A provider-free team facade around a bounded ledger-driven controller."""

    session_persistence_supported = False
    _is_multi_agent_facade = True

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        orchestrator: BaseAgent | MultiAgentOrchestrator,
        agents: Sequence[BaseAgent | AgentBinding],
        settings: MultiAgentSettings | None = None,
        ledger_factory: LedgerFactory | None = None,
        completion_check: CompletionCheck | None = None,
        on_event: MultiAgentEventCallback | None = None,
        description: str = "",
        capabilities: Sequence[str] = (),
        agent_metadata: AgentMetadata | None = None,
        metadata: Mapping[str, Any] | None = None,
        tracer: type[TracerBase] | TracerBase | None = None,
        trace: type[TracerBase] | TracerBase | None = None,
    ) -> None:
        # The facade owns no provider; model and tool authority stays on manager/workers.
        super().__init__(
            name=name,
            system_prompt=system_prompt,
            description=description or "Ledger-driven multi-agent team.",
            capabilities=capabilities,
            agent_metadata=agent_metadata,
            metadata=dict(metadata or {}),
            tracer=tracer,
            trace=trace,
        )
        self._validator = MultiAgentValidator()
        self._orchestrator_template = MagenticOneOrchestrator(orchestrator) if isinstance(orchestrator, BaseAgent) else orchestrator
        self._bindings = self._validator.normalize_bindings(agents)
        self.settings = settings or MultiAgentSettings()
        callbacks = {"ledger_factory": ledger_factory, "completion_check": completion_check, "on_event": on_event}
        self._validator.validate_configuration(self._orchestrator_template, self.settings, callbacks)
        self._bindings_by_owner = {binding.agent.name: binding for binding in self._bindings}
        self._ledger_factory = ledger_factory or MultiAgentPreRunner.default_ledger_factory
        self._completion_check = completion_check
        self._on_event = on_event
        self._active_ledger_ids: set[int] = set()
        self.last_result: MultiAgentResult | None = None
        self.last_ledger: TaskLedgerSnapshot | None = None
        self._initialize_collaborators()

    # @intent bounded-team-controller
    # The facade gives a probabilistic manager bounded authority over a deterministic
    # ledger. One worker may run per round, ordinary post-start failures close their
    # attempts, and only explicit completion gates produce successful termination.
    async def generate_reply(
        self,
        message: str | AgentInput,
        *,
        context: BaseContext | None = None,
        history: Sequence[AgentMessage] = (),
        recipient: str = "orchestrator",
        **options: Any,
    ) -> AgentMessage:
        # Validate inputs, execute one isolated lifecycle, then build the public reply.
        self._validator.validate_generate_options(options)
        request = self._validator.normalize_input(message)
        state = MultiAgentRunState(run_id=uuid.uuid4().hex, request=request, context=context, history=tuple(history))
        self._prepare_public_run_state(request)
        result = await self._lifecycle.execute(state, self._runner.run_with_timeout)
        return await self._post_runner.build_reply(result, request.prompt, recipient, request.metadata)

    def card(self) -> AgentCard:
        # Team identity exposes safe worker summaries without child prompts or live tools.
        cards = (binding.agent.card() for binding in self._bindings)
        workers = tuple({"name": card.name, "description": card.description, "capabilities": tuple(card.capabilities), "tool_names": tuple(card.tool_names)} for card in cards)
        metadata = {**self.metadata, "multi_agent": {"orchestrator": type(self._orchestrator_template).__name__, "workers": workers}}
        return AgentCard(name=self.name, description=self.description, system_prompt=self.system_prompt, capabilities=self.capabilities, metadata=metadata)

    def fork(self, settings: AgentForkSettings | None = None) -> "MultiAgent":
        # Fork manager and worker templates without carrying any live run resources.
        resolved = self._validator.resolve_fork_settings(settings)
        orchestrator = self._validator.validate_orchestrator_fork(self._orchestrator_template.fork())
        bindings = tuple(self._validator.fork_binding_template(binding) for binding in self._bindings)
        child = MultiAgent(
            name=resolved.name or self.name,
            system_prompt=resolved.system_prompt or self.system_prompt,
            orchestrator=orchestrator,
            agents=bindings,
            settings=self.settings,
            ledger_factory=self._ledger_factory,
            completion_check=self._completion_check,
            on_event=self._on_event,
            description=self.description,
            capabilities=self.capabilities,
            agent_metadata=self.agent_metadata,
            metadata={**self.metadata, **dict(resolved.metadata or {})},
            tracer=self._tracer,
        )
        child.history = list(resolved.history) if resolved.history is not None else (list(self.history) if resolved.include_history else [])
        return child

    async def handoff(self, spec: Handoff | None = None, *, by: BaseAgent | None = None) -> Handoff:
        # Teams require an explicit provider-backed handoff generator.
        generator = getattr(by, "generate_handoff", None)
        self._validate_handoff_generator(by, generator, spec)
        assert callable(generator)
        result = await AgentTransfer.maybe_await(generator(HandoffAgent.render_source_run(self)))
        if not isinstance(result, Handoff):
            raise ConfigurationError("MultiAgent handoff generators must return a Handoff instance.", details={"actual_type": type(result).__name__})
        return result

    def add_tool(self, tool: object) -> "MultiAgent":
        # Team-level tools would obscure which child owns execution authority.
        raise ConfigurationError("MultiAgent does not support team-level tools; attach the tool to a manager or worker agent.", details={"tool_type": type(tool).__name__})

    async def attach_mcp_server(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # MCP servers belong on the manager or an explicit worker.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; attach them to manager or worker agents.")

    async def attach_preset_mcp_server(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Preset MCP attachment follows the same explicit child-ownership rule.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; attach them to manager or worker agents.")

    async def attach_mcp_servers(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Batch MCP attachment is also unsupported at the provider-free facade.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; attach them to manager or worker agents.")

    def with_mcp_server(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Deferred MCP configuration remains explicit on a child agent.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; configure manager or worker agents.")

    def with_preset_mcp_server(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Deferred preset configuration remains explicit on a child agent.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; configure manager or worker agents.")

    def persist(self, *, store: SessionStore | None = None, **kwargs: Any) -> Session:
        # Live manager/worker factories and callbacks are not a durable state contract.
        raise ConfigurationError("MultiAgent does not support durable session persistence.")

    def bind_session(self, session: Session) -> "MultiAgent":
        # Session binding cannot imply unsupported team checkpoint semantics.
        raise ConfigurationError("MultiAgent cannot be bound to a durable session.")

    def export_state(self) -> Any:
        # BaseAgent state cannot encode team behavior and ledger semantics safely.
        raise ConfigurationError("MultiAgent state export is unsupported.")

    @classmethod
    def restore(cls, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Restoration remains unavailable until a complete team state contract exists.
        raise ConfigurationError("MultiAgent restoration is unsupported.")

    def _initialize_collaborators(self) -> None:
        # Constructor-owned dependencies make the facade's orchestration protocol visible.
        self._context = MultiAgentContext()
        self._multi_tracer = MultiAgentTracer(self._tracer, self.name)
        self._cleanup = MultiAgentCleanup(self, self._validator)
        self._orchestrator_runner = MultiAgentOrchestratorRunner(self.settings, self._validator, self._multi_tracer)
        self._ledger = MultiAgentOrchestratorLedger(
            self,
            self._validator,
            self._context,
            self._orchestrator_runner,
            self._cleanup,
            self._multi_tracer,
        )
        self._dispatcher = MultiAgentDispatcher(self, self._validator, self._ledger, self._multi_tracer)
        self._pre_runner = MultiAgentPreRunner(self, self._validator)
        self._post_runner = MultiAgentPostRunner(self, self._validator, self._ledger, self._orchestrator_runner)
        self._runner = MultiAgentRunner(
            self,
            self._validator,
            self._pre_runner,
            self._ledger,
            self._dispatcher,
            self._orchestrator_runner,
            self._post_runner,
        )
        self._lifecycle = MultiAgentLifecycle(self, self._validator, self._cleanup, self._multi_tracer)

    def _prepare_public_run_state(self, request: AgentInput) -> None:
        # Public last-result fields reset before any run-local resource is allocated.
        self.last_result = None
        self.last_ledger = None
        self._active_prompt = request.prompt
        self._behavior_view = None

    def _validate_handoff_generator(self, by: BaseAgent | None, generator: Any, spec: Handoff | None) -> None:
        # Validate all handoff compatibility constraints before invoking the provider.
        if by is None or not callable(generator):
            raise ConfigurationError("MultiAgent.handoff requires by=HandoffAgent(...) or a compatible generate_handoff object.")
        generator_spec = getattr(by, "spec", None)
        if spec is not None and generator_spec is None:
            raise ConfigurationError("A compatible MultiAgent handoff generator must expose spec when an explicit spec is supplied.")
        if spec is not None and generator_spec is not None and type(spec) is not type(generator_spec):
            raise ConfigurationError("MultiAgent.handoff spec must match the supplied HandoffAgent spec type.")


__all__ = ["MultiAgent"]
