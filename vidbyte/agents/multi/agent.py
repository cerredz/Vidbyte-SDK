"""Context Protocol Header

Description:
    Implements MultiAgent as a BaseAgent-compatible ledger-driven team facade.
Purpose:
    Owns the bounded plan/delegate/replan/finalize loop, run isolation, finish
    gates, timeout behavior, trace lifecycle, and cleanup across manager/workers.
Architecture:
    - MultiAgent: Public SDK facade and compatibility boundary.
    - _RunState: Private mutable controller counters and run-local resources.
    - Leaf helpers: One orchestration phase, transition, or lifecycle responsibility.
Relations:
    Coordinates ledger.py, orchestrator.py, and transfer.py; exported through vidbyte.agents.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.handoff import HandoffAgent
from vidbyte.agents.multi.ledger import TaskLedger
from vidbyte.agents.multi.orchestrator import MagenticOneOrchestrator, MultiAgentOrchestrator
from vidbyte.agents.multi.transfer import AgentBinding, approve_dispatch, build_worker_request, close_worker, fork_worker, parse_worker_report, validate_worker_report
from vidbyte.agents.multi.types import CompletionCheck, LedgerFactory, MultiAgentEventCallback
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage
from vidbyte.context.handoff import Handoff
from vidbyte.lib.dataclasses.agents import AgentForkSettings, AgentMetadata
from vidbyte.lib.dataclasses.context import BaseContext
from vidbyte.lib.dataclasses.multi_agent import AgentDispatch, AgentReport, FinalizationContext, MultiAgentResult, MultiAgentSettings, OrchestrationContext, OrchestratorDecision, TaskBlocker, TaskLedgerSnapshot
from vidbyte.lib.enums.multi_agent import MultiAgentStopReason, OrchestratorAction, TaskStatus
from vidbyte.lib.errors import AgentTransferError, ConfigurationError, MultiAgentExecutionError, TaskLedgerError
from vidbyte.lib.tracing import TracerBase

if TYPE_CHECKING:
    from vidbyte.sessions.session import Session
    from vidbyte.sessions.store import SessionStore


@dataclass(slots=True)
class _RunState:
    """Private mutable state for one isolated controller invocation."""

    run_id: str
    request: AgentInput
    context: BaseContext | None
    history: tuple[AgentMessage, ...]
    orchestrator: MultiAgentOrchestrator | None = None
    ledger: TaskLedger | None = None
    workers: dict[str, BaseAgent] = field(default_factory=dict)
    rounds: int = 0
    replans: int = 0
    stalls: int = 0
    last_report: AgentReport | None = None
    candidate_answer: str | None = None
    finish_decision: OrchestratorDecision | None = None
    unrecoverable: bool = False
    last_emitted_event_index: int = -1
    cleanup_error_types: tuple[str, ...] = ()
    event_error_types: list[str] = field(default_factory=list)


class MultiAgent(BaseAgent):
    """A BaseAgent-compatible team with a manager-owned task ledger and recovery loop."""

    session_persistence_supported = False

    def __init__(self, *, name: str, system_prompt: str, orchestrator: BaseAgent | MultiAgentOrchestrator, agents: Sequence[BaseAgent | AgentBinding], settings: MultiAgentSettings | None = None, ledger_factory: LedgerFactory | None = None, completion_check: CompletionCheck | None = None, on_event: MultiAgentEventCallback | None = None, description: str = "", capabilities: Sequence[str] = (), agent_metadata: AgentMetadata | None = None, metadata: Mapping[str, Any] | None = None, tracer: type[TracerBase] | TracerBase | None = None, trace: type[TracerBase] | TracerBase | None = None) -> None:
        # Configures a provider-free facade while preserving all model/tool choices on manager and workers.
        super().__init__(name=name, system_prompt=system_prompt, description=description or "Ledger-driven multi-agent team.", capabilities=capabilities, agent_metadata=agent_metadata, metadata=dict(metadata or {}), tracer=tracer, trace=trace)
        self._orchestrator_template = MagenticOneOrchestrator(orchestrator) if isinstance(orchestrator, BaseAgent) else orchestrator
        if not isinstance(self._orchestrator_template, MultiAgentOrchestrator):
            raise ConfigurationError("MultiAgent.orchestrator must be BaseAgent or MultiAgentOrchestrator.", details={"actual_type": type(orchestrator).__name__})
        self._bindings = tuple(item if isinstance(item, AgentBinding) else AgentBinding(item) for item in agents)
        if not self._bindings:
            raise ConfigurationError("MultiAgent requires at least one worker agent.")
        if any(isinstance(binding.agent, MultiAgent) for binding in self._bindings):
            raise ConfigurationError("MultiAgent workers cannot be nested directly in v1; expose a deliberate child team through as_tool() instead.")
        owners = [binding.agent.name for binding in self._bindings]
        if any(not isinstance(owner, str) or not owner.strip() or owner != owner.strip() for owner in owners):
            raise ConfigurationError("MultiAgent worker names must be non-empty strings without surrounding whitespace.", details={"worker_count": len(owners)})
        if len(owners) != len(set(owners)):
            raise ConfigurationError("MultiAgent worker names must be non-empty and unique.", details={"worker_count": len(owners), "unique_worker_count": len(set(owners))})
        self._bindings_by_owner = {binding.agent.name: binding for binding in self._bindings}
        if settings is not None and not isinstance(settings, MultiAgentSettings):
            raise ConfigurationError("MultiAgent.settings must be MultiAgentSettings.", details={"actual_type": type(settings).__name__})
        for label, callback in (("ledger_factory", ledger_factory), ("completion_check", completion_check), ("on_event", on_event)):
            if callback is not None and not callable(callback):
                raise ConfigurationError(f"MultiAgent.{label} must be callable when provided.", details={"actual_type": type(callback).__name__})
        self.settings = settings or MultiAgentSettings()
        self._ledger_factory = ledger_factory or _default_ledger_factory
        self._completion_check = completion_check
        self._on_event = on_event
        self._active_ledger_ids: set[int] = set()
        self.last_result: MultiAgentResult | None = None
        self.last_ledger: TaskLedgerSnapshot | None = None

    # @intent bounded-team-controller
    # The facade gives a probabilistic manager bounded authority over a deterministic
    # ledger. Exactly one worker may run per round, every ordinary post-start failure
    # is converted into a ledger transition, and only explicit completion gates can
    # turn manager intent into a successful terminal answer.
    async def generate_reply(self, message: str | AgentInput, *, context: BaseContext | None = None, history: Sequence[AgentMessage] = (), recipient: str = "orchestrator", **options: Any) -> AgentMessage:
        # Runs one isolated team invocation and returns its finalized BaseAgent-compatible message.
        unsupported_options = sorted(key for key in options if key != "trace_metadata")
        if unsupported_options:
            raise ConfigurationError(f"MultiAgent.generate_reply does not support runner option keys: {', '.join(unsupported_options)}; configure model options on manager or worker agents.")
        if "trace_metadata" in options and not isinstance(options["trace_metadata"], Mapping):
            raise ConfigurationError("MultiAgent trace_metadata must be a mapping when provided.")
        request = self._normalize_team_input(message)
        state = _RunState(run_id=uuid.uuid4().hex, request=request, context=context, history=tuple(history))
        self.last_result = None
        self.last_ledger = None
        self._active_prompt = request.prompt
        self._behavior_view = None
        trace_ctx: Any = None
        run_span: Any = None
        result: MultiAgentResult | None = None
        trace_error: BaseException | None = None
        try:
            trace_ctx = self._tracer.start_trace("agent.run", agent_name=self.name, run_id=state.run_id, strategy="multi_agent")
            run_span = self._tracer.start_span("multi_agent.run", run_id=state.run_id)
            result = await self._run_with_timeout(state)
        except Exception as exc:
            wrapped = exc if isinstance(exc, (ConfigurationError, MultiAgentExecutionError)) else MultiAgentExecutionError("Multi-agent run failed before a safe terminal result.", details={"run_id": state.run_id, "error_type": type(exc).__name__, "rounds": state.rounds, "replans": state.replans})
            trace_error = wrapped
            if wrapped is exc:
                raise
            raise wrapped from exc
        except BaseException as exc:
            trace_error = exc
            raise
        finally:
            try:
                await self._shielded_cleanup(state)
            finally:
                self._active_prompt = ""
                trace_output: str | None = None
                if trace_error is None and result is not None and run_span is not None and trace_ctx is not None:
                    summary = {"run_id": state.run_id, "stop_reason": result.stop_reason.value, "completed": result.completed, "rounds": result.rounds, "replans": result.replans, "revision": result.ledger.revision, "cleanup_errors": len(state.cleanup_error_types)}
                    trace_output = json.dumps(summary, sort_keys=True, separators=(",", ":"))
                try:
                    if run_span is not None:
                        self._tracer.end_span(run_span, output=trace_output, error=trace_error)
                finally:
                    if trace_ctx is not None:
                        self._tracer.end_trace(trace_ctx, output=trace_output, error=trace_error)
        assert result is not None
        return await self._build_reply(result, request.prompt, recipient, request.metadata)

    def card(self) -> AgentCard:
        # Describes team identity and safe worker summaries without exposing child prompts or live tool objects.
        workers = tuple({"name": card.name, "description": card.description, "capabilities": tuple(card.capabilities), "tool_names": tuple(card.tool_names)} for card in (binding.agent.card() for binding in self._bindings))
        metadata = {**self.metadata, "multi_agent": {"orchestrator": type(self._orchestrator_template).__name__, "workers": workers}}
        return AgentCard(name=self.name, description=self.description, system_prompt=self.system_prompt, capabilities=self.capabilities, metadata=metadata)

    def fork(self, settings: AgentForkSettings | None = None) -> "MultiAgent":
        # Rebuilds subtype-preserving manager/worker templates while never sharing run-local ledger state.
        resolved = settings or AgentForkSettings()
        defaults = AgentForkSettings()
        supported = {"name", "system_prompt", "metadata", "include_history", "history"}
        unsupported = sorted(spec.name for spec in fields(resolved) if spec.name not in supported and getattr(resolved, spec.name) != getattr(defaults, spec.name))
        if unsupported:
            raise ConfigurationError(f"MultiAgent.fork does not support override keys: {', '.join(unsupported)}.")
        orchestrator = self._orchestrator_template.fork()
        if inspect.isawaitable(orchestrator):
            if inspect.iscoroutine(orchestrator):
                orchestrator.close()
            raise ConfigurationError("MultiAgentOrchestrator.fork must synchronously return the orchestration protocol.", details={"actual_type": type(orchestrator).__name__})
        if not isinstance(orchestrator, MultiAgentOrchestrator):
            raise ConfigurationError("MultiAgentOrchestrator.fork must preserve the orchestration protocol.", details={"actual_type": type(orchestrator).__name__})
        bindings = tuple(self._fork_binding_template(binding) for binding in self._bindings)
        child = MultiAgent(name=resolved.name or self.name, system_prompt=resolved.system_prompt or self.system_prompt, orchestrator=orchestrator, agents=bindings, settings=self.settings, ledger_factory=self._ledger_factory, completion_check=self._completion_check, on_event=self._on_event, description=self.description, capabilities=self.capabilities, agent_metadata=self.agent_metadata, metadata={**self.metadata, **dict(resolved.metadata or {})}, tracer=self._tracer)
        child.history = list(resolved.history) if resolved.history is not None else (list(self.history) if resolved.include_history else [])
        return child

    async def handoff(self, spec: Handoff | None = None, *, by: BaseAgent | None = None) -> Handoff:
        # Requires an explicit handoff generator because the team facade has no provider of its own.
        generator = getattr(by, "generate_handoff", None)
        if by is None or not callable(generator):
            raise ConfigurationError("MultiAgent.handoff requires by=HandoffAgent(...) or a compatible generate_handoff object.")
        generator_spec = getattr(by, "spec", None)
        if spec is not None and generator_spec is None:
            raise ConfigurationError("A compatible MultiAgent handoff generator must expose spec when an explicit spec is supplied.")
        if spec is not None and generator_spec is not None and type(spec) is not type(generator_spec):
            raise ConfigurationError("MultiAgent.handoff spec must match the supplied HandoffAgent spec type.")
        produced = generator(HandoffAgent.render_source_run(self))
        result = await produced if inspect.isawaitable(produced) else produced
        if not isinstance(result, Handoff):
            raise ConfigurationError("MultiAgent handoff generators must return a Handoff instance.", details={"actual_type": type(result).__name__})
        return result

    def add_tool(self, tool: object) -> "MultiAgent":
        # Rejects team-level tools so execution authority stays explicit on manager or workers.
        raise ConfigurationError("MultiAgent does not support team-level tools; attach the tool to a manager or worker agent.", details={"tool_type": type(tool).__name__})

    async def attach_mcp_server(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Rejects team-level MCP attachment because the facade never executes provider tools.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; attach them to manager or worker agents.")

    async def attach_preset_mcp_server(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Rejects preset MCP attachment at the provider-free team facade.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; attach them to manager or worker agents.")

    async def attach_mcp_servers(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Rejects batch MCP attachment at the provider-free team facade.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; attach them to manager or worker agents.")

    def with_mcp_server(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Rejects deferred MCP configuration at the provider-free team facade.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; configure manager or worker agents.")

    def with_preset_mcp_server(self, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Rejects deferred preset MCP configuration at the provider-free team facade.
        raise ConfigurationError("MultiAgent does not support team-level MCP servers; configure manager or worker agents.")

    def persist(self, *, store: SessionStore | None = None, **kwargs: Any) -> Session:
        # Fails before session construction because team callbacks and live child factories are not serializable.
        raise ConfigurationError("MultiAgent does not support durable session persistence.")

    def bind_session(self, session: Session) -> "MultiAgent":
        # Rejects direct binding so a session cannot imply unsupported team checkpoint semantics.
        raise ConfigurationError("MultiAgent cannot be bound to a durable session.")

    def export_state(self) -> Any:
        # Rejects facade snapshots that would omit manager, worker, transfer, and ledger semantics.
        raise ConfigurationError("MultiAgent state export is unsupported.")

    @classmethod
    def restore(cls, *args: Any, **kwargs: Any) -> "MultiAgent":
        # Rejects restoration because BaseAgent RunState cannot encode team behavior safely.
        raise ConfigurationError("MultiAgent restoration is unsupported.")

    async def _run_with_timeout(self, state: _RunState) -> MultiAgentResult:
        # Applies the hard run budget across initialization, planning, rounds, and finalization.
        if self.settings.run_timeout_seconds is None:
            return await self._execute_run(state)
        try:
            async with asyncio.timeout(self.settings.run_timeout_seconds):
                return await self._execute_run(state)
        except TimeoutError as exc:
            if not self.settings.return_partial_on_limit or not state.candidate_answer or not state.candidate_answer.strip() or state.ledger is None:
                raise MultiAgentExecutionError("Multi-agent run timed out without an allowed candidate answer for partial return.", details={"run_id": state.run_id, "rounds": state.rounds, "replans": state.replans, "candidate_available": bool(state.candidate_answer and state.candidate_answer.strip()), "partial_return_enabled": self.settings.return_partial_on_limit}) from exc
            snapshot = state.ledger.snapshot()
            self.last_ledger = snapshot
            result = MultiAgentResult(content=state.candidate_answer, completed=False, stop_reason=MultiAgentStopReason.TIMEOUT, ledger=snapshot, rounds=state.rounds, replans=state.replans, metadata={"event_callback_error_types": tuple(state.event_error_types)})
            self.last_result = result
            return result

    async def _execute_run(self, state: _RunState) -> MultiAgentResult:
        # Initializes isolated participants, runs controller rounds, then finalizes every non-timeout stop.
        await self._initialize_run(state)
        await self._apply_initial_plan(state)
        stop_reason, completed = await self._run_rounds(state)
        if stop_reason in (MultiAgentStopReason.MAX_ROUNDS, MultiAgentStopReason.MAX_REPLANS, MultiAgentStopReason.UNRECOVERABLE) and not self.settings.return_partial_on_limit:
            raise MultiAgentExecutionError("Multi-agent run reached a configured limit without partial-return permission.", details={"run_id": state.run_id, "stop_reason": stop_reason.value})
        content = await self._finalize_run(state, stop_reason, completed)
        snapshot = self._require_ledger(state).snapshot()
        result = MultiAgentResult(content=content, completed=completed, stop_reason=stop_reason, ledger=snapshot, rounds=state.rounds, replans=state.replans, metadata={"event_callback_error_types": tuple(state.event_error_types)})
        self.last_result = result
        self.last_ledger = snapshot
        return result

    async def _initialize_run(self, state: _RunState) -> None:
        # Forks one orchestrator, one ledger, and one subtype-preserving worker per configured owner.
        orchestrator = self._orchestrator_template.fork()
        if inspect.isawaitable(orchestrator):
            if inspect.iscoroutine(orchestrator):
                orchestrator.close()
            raise ConfigurationError("MultiAgentOrchestrator.fork must synchronously return the orchestration protocol.", details={"actual_type": type(orchestrator).__name__})
        if not isinstance(orchestrator, MultiAgentOrchestrator):
            raise ConfigurationError("MultiAgentOrchestrator.fork must preserve the orchestration protocol.", details={"actual_type": type(orchestrator).__name__})
        state.orchestrator = orchestrator
        owners = tuple(self._bindings_by_owner)
        ledger = self._ledger_factory(state.run_id, state.request, owners, self.settings)
        if inspect.isawaitable(ledger):
            if inspect.iscoroutine(ledger):
                ledger.close()
            raise ConfigurationError("ledger_factory must synchronously return a fresh TaskLedger.", details={"actual_type": type(ledger).__name__})
        if not isinstance(ledger, TaskLedger):
            raise ConfigurationError("ledger_factory must return TaskLedger.", details={"actual_type": type(ledger).__name__})
        initial = ledger.snapshot()
        if initial.run_id != state.run_id or initial.goal != state.request.prompt or initial.revision != 0 or initial.tasks or initial.events:
            raise ConfigurationError("ledger_factory must return a fresh empty TaskLedger for the current run and request.", details={"run_id_matches": initial.run_id == state.run_id, "goal_matches": initial.goal == state.request.prompt, "revision": initial.revision, "task_count": len(initial.tasks), "event_count": len(initial.events)})
        if id(ledger) in self._active_ledger_ids:
            raise ConfigurationError("ledger_factory returned a TaskLedger already active in another run.")
        self._active_ledger_ids.add(id(ledger))
        state.ledger = ledger
        self.last_ledger = initial
        for owner, binding in self._bindings_by_owner.items():
            worker = await fork_worker(binding)
            if any(worker is existing for existing in state.workers.values()):
                raise AgentTransferError("Worker fork factories must return a distinct run-local instance per owner.", details={"owner": owner})
            state.workers[owner] = worker

    async def _apply_initial_plan(self, state: _RunState) -> None:
        # Requests and atomically commits the first manager plan before any worker can run.
        context = self._orchestration_context(state)
        plan = await self._call_orchestrator(state, "plan", self._require_orchestrator(state).plan(context))
        self._require_ledger(state).apply_plan(plan)
        await self._after_ledger_commit(state, "plan_applied")

    async def _run_rounds(self, state: _RunState) -> tuple[MultiAgentStopReason, bool]:
        # Executes one serial action per round until completion, partial finish, or a finite limit.
        while state.rounds < self.settings.max_rounds:
            state.rounds += 1
            replanned_this_round = False
            decision = await self._call_orchestrator(state, "decide", self._require_orchestrator(state).decide(self._orchestration_context(state)))
            self._remember_candidate(state, decision)
            if decision.next_action is not None:
                self._require_ledger(state).set_next_action(decision.next_action)
                await self._after_ledger_commit(state, "next_action")
            if decision.action is OrchestratorAction.FINISH:
                outcome = await self._handle_finish_decision(state, decision)
                if outcome is not None:
                    return outcome
            elif decision.action is OrchestratorAction.REPLAN:
                replanned_this_round = True
                if not await self._try_replan(state):
                    return MultiAgentStopReason.MAX_REPLANS, False
                if state.unrecoverable:
                    return MultiAgentStopReason.UNRECOVERABLE, False
            else:
                progressed = await self._delegate_once(state, decision)
                failed_report = state.last_report is not None and state.last_report.task_id == decision.task_id and state.last_report.status in (TaskStatus.FAILED, TaskStatus.BLOCKED)
                state.stalls = max(0, state.stalls - 1) if progressed and not decision.loop_detected and not failed_report else state.stalls + 1
            if not replanned_this_round and state.stalls >= self.settings.replan_after_stalls:
                if not await self._try_replan(state):
                    return MultiAgentStopReason.MAX_REPLANS, False
                if state.unrecoverable:
                    return MultiAgentStopReason.UNRECOVERABLE, False
        return MultiAgentStopReason.MAX_ROUNDS, False

    async def _handle_finish_decision(self, state: _RunState, decision: OrchestratorDecision) -> tuple[MultiAgentStopReason, bool] | None:
        # Accepts full completion only through gates, or an explicit candidate through partial policy.
        if await self._finish_gate_passes(state, decision):
            state.finish_decision = decision
            return MultiAgentStopReason.COMPLETED, True
        if self.settings.allow_partial_finish and state.candidate_answer and state.candidate_answer.strip():
            state.finish_decision = decision
            return MultiAgentStopReason.PARTIAL, False
        self._require_ledger(state).record_decision_rejection("Finish rejected because completion gates are not satisfied.")
        await self._after_ledger_commit(state, "finish_rejected")
        state.stalls += 1
        return None

    async def _delegate_once(self, state: _RunState, decision: OrchestratorDecision) -> bool:
        # Starts one ready ledger task, runs its configured transfer boundary, and commits its report.
        ledger = self._require_ledger(state)
        assert decision.task_id is not None and decision.owner is not None and decision.instruction is not None
        try:
            record = ledger.task(decision.task_id)
            dispatch = AgentDispatch(run_id=state.run_id, base_revision=ledger.revision, task_id=record.task_id, owner=decision.owner, goal=record.goal, acceptance_criteria=record.acceptance_criteria, instruction=decision.instruction, payload=record.payload if decision.payload is None else decision.payload, attempt=record.attempts + 1, metadata={"round": state.rounds})
            ledger.start_task(dispatch)
            await self._after_ledger_commit(state, "task_started")
        except (TaskLedgerError, ValueError):
            ledger.record_decision_rejection("Delegate decision rejected by ledger readiness or ownership checks.", task_id=decision.task_id, owner=decision.owner)
            await self._after_ledger_commit(state, "delegate_rejected")
            return False
        return await self._execute_dispatch(state, dispatch)

    async def _execute_dispatch(self, state: _RunState, dispatch: AgentDispatch) -> bool:
        # Contains every ordinary post-start failure so no normal path strands IN_PROGRESS state.
        ledger = self._require_ledger(state)
        binding = self._bindings_by_owner.get(dispatch.owner)
        try:
            if binding is None:
                raise AgentTransferError("Dispatch owner has no configured worker binding.", details={"owner": dispatch.owner})
            transfer_snapshot = ledger.snapshot()
            blocker = await approve_dispatch(binding.transfer, dispatch, transfer_snapshot)
            if blocker is not None:
                report = AgentReport(task_id=dispatch.task_id, status=TaskStatus.BLOCKED, blockers=(blocker,))
            else:
                request = await build_worker_request(binding.transfer, dispatch, transfer_snapshot)
                reply = await self._invoke_worker(state, binding, dispatch, request)
                parsed = await parse_worker_report(binding.transfer, reply, dispatch, ledger.snapshot())
                report = await validate_worker_report(binding.transfer, parsed, dispatch, ledger.snapshot())
            state.last_report = report
            _, progressed = ledger.apply_report(report, owner=dispatch.owner)
            await self._after_ledger_commit(state, "task_reported")
            return progressed
        except Exception as exc:
            blocker = TaskBlocker(code="dispatch_boundary_error", message="Worker dispatch failed at a configured transfer boundary.", retryable=True, metadata={"error_type": type(exc).__name__})
            ledger.record_dispatch_failure(dispatch.task_id, owner=dispatch.owner, blocker=blocker)
            await self._after_ledger_commit(state, "dispatch_failed")
            return False

    async def _invoke_worker(self, state: _RunState, binding: AgentBinding, dispatch: AgentDispatch, request: str | AgentInput) -> AgentMessage:
        # Retries transient invocation failures inside one ledger attempt and applies the effective worker timeout.
        worker = state.workers[dispatch.owner]
        span = self._tracer.start_span("multi_agent.worker", run_id=state.run_id, task_id=dispatch.task_id, owner=dispatch.owner, attempt=dispatch.attempt, round=state.rounds)
        timeout = binding.transfer.timeout_seconds or self.settings.worker_timeout_seconds
        last_error: Exception | None = None
        try:
            for invocation in range(binding.transfer.max_invocation_retries + 1):
                try:
                    call = worker.generate_reply(request, recipient=self.name, trace_metadata={"multi_agent_run_id": state.run_id, "task_id": dispatch.task_id, "owner": dispatch.owner, "attempt": dispatch.attempt, "invocation": invocation + 1})
                    reply = await call if timeout is None else await asyncio.wait_for(call, timeout=timeout)
                    self._tracer.end_span(span, output=_trace_output(status="reported", invocation=invocation + 1))
                    return reply
                except Exception as exc:
                    last_error = exc
            raise AgentTransferError("Worker invocation failed after bounded retries.", details={"task_id": dispatch.task_id, "owner": dispatch.owner, "attempts": binding.transfer.max_invocation_retries + 1, "error_type": type(last_error).__name__ if last_error else "UnknownWorkerError"}) from last_error
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def _try_replan(self, state: _RunState) -> bool:
        # Replaces future work within budget and resets only workers configured for plan-cycle isolation.
        if state.replans >= self.settings.max_replans:
            return False
        ledger = self._require_ledger(state)
        before = ledger.snapshot()
        before_ready = tuple(sorted(task.task_id for task in before.tasks if task.status is not TaskStatus.SUPERSEDED and ledger.is_ready(task.task_id)))
        span = self._tracer.start_span("multi_agent.replan", run_id=state.run_id, replans=state.replans, round=state.rounds, stalls=state.stalls, revision=ledger.revision)
        try:
            plan = await self._call_orchestrator(state, "replan", self._require_orchestrator(state).replan(self._orchestration_context(state)))
            ledger.apply_plan(plan, replan=True)
            state.replans += 1
            after = ledger.snapshot()
            after_ready = tuple(sorted(task.task_id for task in after.tasks if task.status is not TaskStatus.SUPERSEDED and ledger.is_ready(task.task_id)))
            material_change = _replan_signature(before) != _replan_signature(after) or before_ready != after_ready
            state.stalls = 0 if material_change else 1
            state.unrecoverable = ledger.required_work_is_unrecoverable()
            await self._after_ledger_commit(state, "plan_replaced")
            await self._reset_workers(state)
            self._tracer.end_span(span, output=_trace_output(revision=ledger.revision, replans=state.replans, material_change=material_change, unrecoverable=state.unrecoverable))
            return True
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def _reset_workers(self, state: _RunState) -> None:
        # Attempts every selected worker reset and reports safe aggregate failure context afterward.
        errors: list[tuple[str, str]] = []
        for owner, binding in self._bindings_by_owner.items():
            if not binding.transfer.reset_on_replan:
                continue
            worker = state.workers[owner]
            try:
                await close_worker(binding, worker)
            except Exception as exc:
                errors.append((owner, type(exc).__name__))
                continue
            state.workers.pop(owner)
            try:
                replacement = await fork_worker(binding)
                if any(replacement is existing for existing_owner, existing in state.workers.items() if existing_owner != owner):
                    raise AgentTransferError("Worker reset factory returned an instance already assigned to another owner.", details={"owner": owner})
                state.workers[owner] = replacement
            except Exception as exc:
                errors.append((owner, type(exc).__name__))
        if errors:
            raise MultiAgentExecutionError("One or more workers could not be safely reset after replanning.", details={"failures": tuple({"owner": owner, "error_type": error_type} for owner, error_type in errors)})

    async def _finish_gate_passes(self, state: _RunState, decision: OrchestratorDecision) -> bool:
        # Combines structural completion, optional evidence proof, and the developer completion callback.
        ledger = self._require_ledger(state)
        if not ledger.all_required_complete():
            return False
        if self.settings.require_verified_evidence and not ledger.required_tasks_have_verified_evidence():
            return False
        if self._completion_check is None:
            return True
        result = self._completion_check(self._orchestration_context(state), decision)
        return bool(await result) if inspect.isawaitable(result) else bool(result)

    async def _finalize_run(self, state: _RunState, stop_reason: MultiAgentStopReason, completed: bool) -> str:
        # Gives the schema-free manager one terminal synthesis call for every non-timeout outcome.
        final_context = FinalizationContext(orchestration=self._orchestration_context(state), stop_reason=stop_reason, completed=completed, candidate_answer=state.candidate_answer, finish_decision=state.finish_decision)
        span = self._tracer.start_span("multi_agent.finalize", run_id=state.run_id, reason=stop_reason.value, rounds=state.rounds, replans=state.replans, revision=self._require_ledger(state).revision)
        try:
            content = await self._await_orchestrator(self._require_orchestrator(state).finalize(final_context))
            if not isinstance(content, str) or not content.strip():
                raise MultiAgentExecutionError("Multi-agent finalizer must return a non-blank string.", details={"stop_reason": stop_reason.value})
            self._tracer.end_span(span, output=_trace_output(status="finalized", reason=stop_reason.value))
            return content
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def _call_orchestrator(self, state: _RunState, phase: str, awaitable: Any) -> Any:
        # Applies the manager timeout and records only safe phase/counter attributes in tracing.
        span = self._tracer.start_span("multi_agent.orchestrator", run_id=state.run_id, phase=phase, round=state.rounds, replans=state.replans, stalls=state.stalls, revision=self._require_ledger(state).revision)
        try:
            result = await self._await_orchestrator(awaitable)
            self._tracer.end_span(span, output=_trace_output(phase=phase, status="completed"))
            return result
        except TimeoutError as exc:
            wrapped = MultiAgentExecutionError("Multi-agent orchestrator phase exceeded its configured timeout.", details={"phase": phase, "round": state.rounds, "timeout_seconds": self.settings.orchestrator_timeout_seconds})
            self._tracer.end_span(span, error=wrapped)
            raise wrapped from exc
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def _await_orchestrator(self, awaitable: Any) -> Any:
        # Awaits one orchestrator phase under the optional per-phase timeout.
        timeout = self.settings.orchestrator_timeout_seconds
        return await awaitable if timeout is None else await asyncio.wait_for(awaitable, timeout=timeout)

    async def _after_ledger_commit(self, state: _RunState, status: str) -> None:
        # Updates public snapshots, traces the revision, and emits each retained event at most once.
        ledger = self._require_ledger(state)
        snapshot = ledger.snapshot()
        self.last_ledger = snapshot
        span = self._tracer.start_span("multi_agent.ledger_update", run_id=state.run_id, revision=snapshot.revision, status=status)
        event = ledger.latest_event
        if self._on_event is None or event is None or event.index <= state.last_emitted_event_index:
            self._tracer.end_span(span, output=_trace_output(revision=snapshot.revision, status=status))
            return
        state.last_emitted_event_index = event.index
        try:
            emitted = self._on_event(event, snapshot)
            if inspect.isawaitable(emitted):
                await emitted
            self._tracer.end_span(span, output=_trace_output(revision=snapshot.revision, status=status, event_callback="completed"))
        except Exception as exc:
            state.event_error_types.append(type(exc).__name__)
            self._tracer.end_span(span, output=_trace_output(revision=snapshot.revision, status=status, event_callback="failed", error_type=type(exc).__name__))

    def _orchestration_context(self, state: _RunState) -> OrchestrationContext:
        # Builds the explicit manager context while default rendering still excludes history and BaseContext.
        return OrchestrationContext(request=state.request, team_instructions=self.system_prompt, team=tuple(binding.agent.card() for binding in self._bindings), ledger=self._require_ledger(state).snapshot(), settings=self.settings, context=state.context, history=(*self.history, *state.history), round=state.rounds, replans=state.replans, stalls=state.stalls, last_report=state.last_report)

    def _remember_candidate(self, state: _RunState, decision: OrchestratorDecision) -> None:
        # Retains the latest non-blank manager candidate solely for hard-timeout fallback.
        if isinstance(decision.final_answer, str) and decision.final_answer.strip():
            state.candidate_answer = decision.final_answer

    async def _build_reply(self, result: MultiAgentResult, request: str, recipient: str, input_metadata: Mapping[str, Any]) -> AgentMessage:
        # Records the final team message and drains queued prompts only after run-local cleanup completed.
        metadata: dict[str, Any] = {**dict(input_metadata), "strategy": "multi_agent", "multi_agent": {"stop_reason": result.stop_reason.value, "completed": result.completed, "rounds": result.rounds, "replans": result.replans, "ledger_revision": result.ledger.revision, "result": result, "ledger": result.ledger}}
        reply = AgentMessage(sender=self.name, recipient=recipient, content=result.content, metadata=metadata)
        self.history.append(reply)
        self.last_prompt = request
        self.last_reply = reply
        if self._queued_prompts and not self._draining_queued_prompts:
            await self._drain_queued_prompts(metadata)
        return reply

    async def _shielded_cleanup(self, state: _RunState) -> None:
        # Lets participant cleanup finish even when the run is being cancelled or timed out.
        task = asyncio.create_task(self._cleanup_run(state))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise

    async def _cleanup_run(self, state: _RunState) -> None:
        # Closes every run-local worker and manager independently so one closer cannot skip another.
        unique_workers: dict[int, tuple[AgentBinding, BaseAgent]] = {}
        for owner, worker in tuple(state.workers.items()):
            unique_workers.setdefault(id(worker), (self._bindings_by_owner[owner], worker))
        closers = [close_worker(binding, worker) for binding, worker in unique_workers.values()]
        state.workers.clear()
        if state.ledger is not None:
            self._active_ledger_ids.discard(id(state.ledger))
        if state.orchestrator is not None:
            closers.append(state.orchestrator.aclose())
            state.orchestrator = None
        if closers:
            outcomes = await asyncio.gather(*closers, return_exceptions=True)
            state.cleanup_error_types = tuple(type(outcome).__name__ for outcome in outcomes if isinstance(outcome, BaseException))

    def _fork_binding_template(self, binding: AgentBinding) -> AgentBinding:
        # Forks a child template synchronously so MultiAgent.fork preserves each worker's behavioral subtype.
        try:
            child = binding.agent.fork(binding.transfer.fork_settings) if binding.fork_factory is None else binding.fork_factory(binding.agent, binding.transfer.fork_settings)
        except Exception as exc:
            raise ConfigurationError("MultiAgent.fork could not construct an isolated worker template.", details={"worker": binding.agent.name, "error_type": type(exc).__name__}) from exc
        if inspect.isawaitable(child):
            if inspect.iscoroutine(child):
                child.close()
            raise ConfigurationError("MultiAgent.fork requires synchronous worker fork factories.", details={"worker": binding.agent.name})
        if not isinstance(child, BaseAgent) or not isinstance(child, type(binding.agent)) or child is binding.agent:
            raise ConfigurationError("MultiAgent.fork requires synchronous subtype-preserving worker fork factories.", details={"worker": binding.agent.name, "expected_type": type(binding.agent).__name__, "actual_type": type(child).__name__})
        return AgentBinding(agent=child, transfer=binding.transfer, fork_factory=binding.fork_factory, closer=binding.closer)

    def _normalize_team_input(self, message: str | AgentInput) -> AgentInput:
        # Preserves typed input metadata/context while normalizing plain strings to the shared contract.
        if isinstance(message, AgentInput):
            if isinstance(message.prompt, str) and message.prompt.strip():
                return message
            raise MultiAgentExecutionError("MultiAgent AgentInput.prompt must be a non-blank string.")
        if isinstance(message, str) and message.strip():
            return AgentInput(prompt=message)
        raise MultiAgentExecutionError("MultiAgent input must be a non-blank string or AgentInput.")

    def _require_ledger(self, state: _RunState) -> TaskLedger:
        # Returns initialized ledger state or fails with a safe lifecycle error.
        if state.ledger is None:
            raise MultiAgentExecutionError("Multi-agent ledger is not initialized.", details={"run_id": state.run_id})
        return state.ledger

    def _require_orchestrator(self, state: _RunState) -> MultiAgentOrchestrator:
        # Returns the run-local orchestrator or fails with a safe lifecycle error.
        if state.orchestrator is None:
            raise MultiAgentExecutionError("Multi-agent orchestrator is not initialized.", details={"run_id": state.run_id})
        return state.orchestrator


def _default_ledger_factory(run_id: str, request: AgentInput, owners: tuple[str, ...], settings: MultiAgentSettings) -> TaskLedger:
    # Constructs the standard in-memory TaskLedger without introducing persistence semantics.
    return TaskLedger(run_id=run_id, goal=request.prompt, owners=owners, settings=settings, metadata={})


def _trace_output(**fields: Any) -> str:
    # Encodes small control-only trace results through the TracerBase string contract.
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))


def _replan_signature(snapshot: TaskLedgerSnapshot) -> tuple[Any, ...]:
    # Captures control-relevant plan facts without invoking equality on opaque developer values.
    active = tuple(sorted((task.task_id, task.goal, task.owner, task.depends_on, task.required, task.acceptance_criteria, task.max_attempts, _value_fingerprint(task.payload), _value_fingerprint(dict(task.metadata))) for task in snapshot.tasks if task.status is not TaskStatus.SUPERSEDED))
    facts = (snapshot.verified_facts, snapshot.facts_to_find, snapshot.facts_to_derive, snapshot.educated_guesses)
    return active, facts


def _value_fingerprint(value: Any) -> str:
    # Uses deterministic JSON when safe and identity-only markers for opaque values.
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return f"opaque:{type(value).__module__}.{type(value).__qualname__}:{id(value)}"


__all__ = ["MultiAgent"]
