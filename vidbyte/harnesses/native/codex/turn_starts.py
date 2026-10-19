"""FILE: vidbyte/harnesses/native/codex/turn_starts.py

PURPOSE: CodexTurnStarts, the CodexHost collaborator that starts every turn that spends: a plain turn, a goal run, and the resume of a stored goal. Each start is sent once through CodexConnection.start, so a start whose caller left is still adopted and stopped; accept then watches the started turn, or ends it as exited when close or a death came first, and release_tools drops the tool handler of a thread whose first turn never started.
ROLE IN CODEBASE: A host collaborator of vidbyte/harnesses/native/codex/; CodexHost._open builds it, spawn, continue and launch call it from host.py, and the side chat and goal resume call it from the thread and goal mixins (first-class D-2).
ARCHITECTURE NOTE: Loads openai-codex at module level, for the SDK's own CodexError and JsonRpcError, so only CodexHost._open imports this module (first-class INV-45). Every client call here runs inside CodexConnection.start's worker or a bounded CodexConnection.call, so it writes one call record (INV-3). The goal resume's worker is one method run inside connection.start under CODEX_GOAL_RESUME_CALL; its start window is read from this module's namespace at call time, so a test patches it here.
COMMON MODIFICATION PATTERNS: A new kind of spending start is one public method here built the same way: one worker or SDK call inside connection.start, a private adopt-late method that registers then stops a late start, and the registry's track or track_goal. A check a start needs before it sends goes in the method, before connection.start, with its message in vidbyte/lib/constants/codex_host.py.
KNOWN EDGE CASES: A collaboration mode needs a model on the wire, so a mode turn on a thread Codex reported no model for, with no mode or turn model, is refused before turn/start (first-class INV-13, EC-14). A goal run registers only once its budget echo matches (INV-25). A resume cancels its goal operation from the moment its status set is sent, unless Codex answered the set with a JSON-RPC error, which is a refusal that changed nothing; an answer that does not validate counts as sent and is cancelled (EC-64). It always finishes and unregisters the operation (EC-37, EC-38); its start window elapsing is codex.api_error. Close wins over a turn still starting (EC-79).
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 8.1 D-2 and D-17, 8.5 and 12.3 row 22, INV-3, INV-13, INV-31); docs/spec/codex-host/spec.md (INV-11, INV-25, D-35, EC-79); docs/spec/codex-host-hardening/spec.md (INV-26)
TESTS: tests/features/codex_host/test_codex_host_turns.py, tests/features/codex_host/test_codex_host_review_goals.py, tests/features/codex_host/test_codex_host_settings_modes.py, tests/features/codex_host/test_codex_host_goal_control.py, tests/features/codex_host/test_codex_host_side_chat.py, tests/features/codex_host/test_codex_host_resilience.py
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING, Any

from openai_codex.errors import CodexError, JsonRpcError

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.harnesses.native.codex.feature_wire import CodexFeatureParamsTranslator
from vidbyte.lib.constants.codex import (
    CODEX_GOAL_CANCEL_CALL,
    CODEX_GOAL_SET_METHOD,
    CODEX_TURN_START_METHOD,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_GOAL_RESUME_CALL,
    CODEX_GOAL_START_CALL,
    CODEX_HOST_BUDGET_ECHO_MESSAGE,
    CODEX_HOST_GOAL_RESUME_START_SECONDS,
    CODEX_HOST_MODE_MODEL_MISSING_CAUSE,
    CODEX_HOST_MODE_MODEL_MISSING_MESSAGE,
    CODEX_HOST_MODE_MODEL_MISSING_NEXT_STEP,
)
from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle
from vidbyte.lib.enums.codex import CodexGoalStatus
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError

if TYPE_CHECKING:
    from openai_codex._goal import _GoalOperationState
    from openai_codex.generated.v2_all import TurnStartResponse

    from vidbyte.harnesses.native.codex.connection import CodexConnection
    from vidbyte.harnesses.native.codex.turn_events import CodexTurnEvents
    from vidbyte.harnesses.native.codex.turns import (
        CodexLiveTurn,
        CodexTurnRegistry,
    )
    from vidbyte.harnesses.native.codex.wire import (
        CodexParamsTranslator,
        CodexResponseTranslator,
    )
    from vidbyte.lib.dataclasses.codex import CodexAgentSettings
    from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest
    from vidbyte.lib.enums.codex import CodexHostOperation


class CodexTurnStarts:
    """Starts the turns, goal runs and goal resumes of one CodexHost, and owns each one Codex accepts."""

    def __init__(
        self,
        connection: CodexConnection,
        params: CodexParamsTranslator,
        responses: CodexResponseTranslator,
        registry: CodexTurnRegistry,
        events: CodexTurnEvents,
    ) -> None:
        # The host's own parts, built once the host opened.
        self._connection = connection
        self._params = params
        self._responses = responses
        self._registry = registry
        self._events = events

    async def start_turn(
        self,
        operation: CodexHostOperation,
        thread_id: str,
        request: CodexSpawnRequest,
        items: list[dict[str, Any]],
        pricing: CodexAgentSettings,
    ) -> CodexLiveTurn:
        # @intent own-the-turn-even-when-its-caller-left
        # turn/start spends, so it is sent once. If its caller leaves
        # first, the turn is still adopted when Codex accepts it
        # (INV-11).
        # A collaboration mode must carry a model: the mode's, the
        # turn's, or the one Codex resolved for the thread. With none,
        # the turn is refused before it is sent (first-class INV-13).
        resolved = pricing.thread.model
        mode = request.collaboration_mode
        if mode is not None and not (mode.model or request.turn.model or resolved):
            raise CodexErrorMapper.error(
                FailureCode.CODEX_PROTOCOL_MISMATCH,
                CODEX_HOST_MODE_MODEL_MISSING_MESSAGE,
                operation,
                thread_id,
                likely_cause=CODEX_HOST_MODE_MODEL_MISSING_CAUSE,
                next_step=CODEX_HOST_MODE_MODEL_MISSING_NEXT_STEP,
            )
        connection = self._connection
        start = partial(connection.client.turn_start, thread_id, items, self._params.turn_start(thread_id, request, resolved))
        adopt = partial(self._adopt_late_turn, thread_id, request, pricing)
        response = await connection.start(operation, CODEX_TURN_START_METHOD, start, adopt, thread_id=thread_id)
        return self._registry.track(CodexTurnHandle(thread_id=thread_id, turn_id=response.turn.id), request, pricing)

    async def start_goal(
        self,
        operation: CodexHostOperation,
        thread_id: str,
        request: CodexSpawnRequest,
        goal: CodexGoal,
        pricing: CodexAgentSettings,
    ) -> CodexLiveTurn:
        # @intent a-goal-run-registers-only-after-its-budget-holds
        # openai-codex starts the goal; its token budget is then set on
        # its own, once, and must come back unchanged. Any failure
        # before the run is registered cancels it and releases its
        # stream (INV-25).
        connection = self._connection
        start = partial(connection.client.start_goal_operation, thread_id, goal.objective)
        adopt = partial(self._adopt_late_goal, thread_id, request, pricing)
        state, turn_id = await connection.start(operation, CODEX_GOAL_START_CALL, start, adopt, thread_id=thread_id)
        try:
            if goal.token_budget is not None and not connection.stopped():
                budget_call = connection.raw(CODEX_GOAL_SET_METHOD, self._params.goal_budget(thread_id, goal.token_budget))
                echoed = await connection.call(operation, CODEX_GOAL_SET_METHOD, budget_call, thread_id=thread_id)
                if echoed.goal.token_budget != goal.token_budget:
                    echo = CODEX_HOST_BUDGET_ECHO_MESSAGE.format(stored=echoed.goal.token_budget, sent=goal.token_budget)
                    raise CodexErrorMapper.error(FailureCode.CODEX_PROTOCOL_MISMATCH, echo, operation, thread_id)
        except BaseException:
            # The stream is released even if a second cancellation lands
            # while the cancel is awaited (INV-25).
            try:
                with suppress(CodexAgentError):
                    await connection.call(operation, CODEX_GOAL_CANCEL_CALL, connection.client.cancel_goal_operation, state, thread_id=thread_id, cleanup=True)
            finally:
                state.finish()
                connection.client.unregister_goal_operation(state)
            raise
        return self._registry.track_goal(CodexTurnHandle(thread_id=thread_id, turn_id=turn_id), request, pricing, state)

    async def resume_goal(
        self,
        operation: CodexHostOperation,
        thread_id: str,
        request: CodexSpawnRequest,
        pricing: CodexAgentSettings,
    ) -> CodexLiveTurn:
        # @intent a-resume-keeps-the-stored-goal-and-owns-its-run
        # A resume sets the stored goal back to active with a
        # status-only set, which keeps its objective, budget and usage,
        # rather than starting a new goal, which would clear it first
        # (first-class D-17). The whole step is one spending start, so
        # a resume whose caller left is still adopted and stopped once,
        # like a goal run (EC-38), and it is tracked exactly like one.
        connection = self._connection
        activate = connection.raw(CODEX_GOAL_SET_METHOD, CodexFeatureParamsTranslator.goal_change(thread_id, status=CodexGoalStatus.ACTIVE))
        start = partial(self._resume_now, thread_id, activate)
        adopt = partial(self._adopt_late_goal, thread_id, request, pricing)
        state, turn_id = await connection.start(operation, CODEX_GOAL_RESUME_CALL, start, adopt, thread_id=thread_id)
        return self._registry.track_goal(CodexTurnHandle(thread_id=thread_id, turn_id=turn_id), request, pricing, state)

    def accept(self, operation: CodexHostOperation, turn: CodexLiveTurn) -> CodexTurnHandle:
        # @intent close-wins-over-a-starting-turn
        # A turn accepted after close began or the process died ends as
        # exited, and its caller gets process_exited naming the thread
        # (EC-79). Otherwise one watcher and the turn's timer start.
        connection = self._connection
        if connection.stopped():
            self._registry.finish(turn, self._responses.exited(turn.handle))
            if turn.state is None:
                connection.client.unregister_turn_notifications(turn.handle.turn_id)
            turn.close_goal_stream(connection.client)
            raise CodexErrorMapper.process_exited(operation, turn.handle.thread_id)
        turn.watch(connection, self._events.on_event, self._events.on_lost)
        return turn.handle

    def release_tools(self, thread_id: str) -> None:
        # A thread whose first turn failed to start keeps no tool
        # handler, unless that start is still in flight and its turn
        # will be adopted (hardening INV-26).
        connection = self._connection
        if not connection.starting(thread_id):
            connection.router.unregister(thread_id)

    def _resume_now(self, thread_id: str, activate: Callable[[], Any]) -> tuple[_GoalOperationState, str]:
        # @intent a-resume-cancels-a-set-codex-did-not-refuse
        # Runs on a host worker inside connection.start, in
        # openai-codex's own goal-start order without its clear: route
        # the goal's turns to one goal operation, set the goal active
        # once, then wait for Codex's first turn within the resume
        # window, read now. From the moment the set is sent, a failure
        # cancels the operation, unless Codex answered the set with a
        # JSON-RPC error: that is a refusal, so the goal never changed.
        # An answer that does not validate may still have been applied,
        # so it is cancelled. The operation is always finished and
        # unregistered, so nothing is left routed; a cancel that fails
        # is ignored, so the caller sees why the resume failed
        # (first-class INV-31, EC-37, EC-38, EC-64).
        client = self._connection.client
        state = client.reserve_goal_operation(thread_id)
        sent = False
        try:
            state.activate_turn_routing()
            sent = True
            activate()
            turn_id = state.wait_for_start(CODEX_HOST_GOAL_RESUME_START_SECONDS)
            if turn_id is None:
                raise CodexError
            return state, turn_id
        except BaseException as exc:
            with suppress(Exception):
                if sent and not isinstance(exc, JsonRpcError):
                    client.cancel_goal_operation(state)
            state.finish()
            client.unregister_goal_operation(state)
            raise

    def _adopt_late_turn(self, thread_id: str, request: CodexSpawnRequest, pricing: CodexAgentSettings, response: TurnStartResponse) -> None:
        # @intent a-late-turn-is-owned-then-stopped
        # Runs on the loop when turn/start returns after its caller
        # left. The turn is registered, so a get finds it, and stopped
        # with one interrupt that carries no stop reason (D-35); close
        # wins (EC-79).
        turn = self._registry.track(CodexTurnHandle(thread_id=thread_id, turn_id=response.turn.id), request, pricing)
        connection = self._connection
        if connection.stopped():
            connection.client.unregister_turn_notifications(turn.handle.turn_id)
            self._registry.finish(turn, self._responses.exited(turn.handle))
            return
        turn.watch(connection, self._events.on_event, self._events.on_lost)
        turn.stop(connection, None)

    def _adopt_late_goal(
        self,
        thread_id: str,
        request: CodexSpawnRequest,
        pricing: CodexAgentSettings,
        started: tuple[_GoalOperationState, str],
    ) -> None:
        # @intent a-late-goal-run-is-owned-then-stopped
        # The goal-run twin of _adopt_late_turn, for a goal start or a
        # goal resume: registered, then stopped with one cancel, or
        # ended as exited when close came first.
        state, turn_id = started
        turn = self._registry.track_goal(CodexTurnHandle(thread_id=thread_id, turn_id=turn_id), request, pricing, state)
        connection = self._connection
        if connection.stopped():
            self._registry.finish(turn, self._responses.exited(turn.handle))
            turn.close_goal_stream(connection.client)
            return
        turn.watch(connection, self._events.on_event, self._events.on_lost)
        turn.stop(connection, None)


__all__ = ["CodexTurnStarts"]
