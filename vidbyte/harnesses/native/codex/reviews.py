"""FILE: vidbyte/harnesses/native/codex/reviews.py

PURPOSE: CodexReviews, the CodexHost collaborator behind start_codex_review: it checks the thread and the account, sends review/start once, registers the review turn with the caller's time and output caps, reads it back from one page, and owns a review whose caller left.
ROLE IN CODEBASE: A host collaborator of vidbyte/harnesses/native/codex/; CodexHost builds it in _open() after CodexTurnEvents, and start_codex_review guards, builds its CodexReviewRequest, then delegates here. Review turns are watched through CodexTurnEvents like any other turn.
ARCHITECTURE NOTE: Reaches Codex only through CodexConnection, builds params with CodexParamsTranslator and records with CodexResponseTranslator, and reads review turns back through CodexThreadHelpers.review_turn. It imports no openai-codex module at module level, and its collaborators only under TYPE_CHECKING, so importing CodexHost still loads no SDK module (codex-host D-21, hardening INV-41).
FUNCTION INVENTORY: start(operation, review) checks, sends one review/start, registers the turn and returns its handle once read back; _adopt_late(operation, request, pricing, response) registers a review whose caller left and reads it back in the background; _track(response, request, pricing) registers the review turn under the request's caps; _accept(operation, turn, late=...) reads a registered review back and either ends it from what Codex stored, failing it through CodexTurnEvents.fail when that end cannot be built, or watches it.
COMMON MODIFICATION PATTERNS: A new review argument is a field on CodexReviewRequest in vidbyte/lib/dataclasses/codex_host_inputs.py and, if Codex takes it, one key in CodexParamsTranslator.review; a cap Vidbyte enforces itself stays on the review's CodexSpawnRequest.
WHAT NOT TO DO: Do not read a review back with thread/read includeTurns; one review_read_back page holds the review turn (hardening INV-38). Do not retry review/start: it spends, so it is sent once, and a start that outlives its caller is adopted and stopped once (codex-host INV-11). Do not register a review turn under a fresh CodexSpawnRequest, or its caps are lost (hardening INV-30).
KNOWN EDGE CASES: openai-codex drops a review turn's events that arrive before registration, so every review is read back after registering (D-23); a review that already ended is built from what was read back, and one whose snapshot cannot be built ends FAILED codex.protocol_mismatch, as a turn whose events fail does (hardening INV-12). A caller cancelled during the read-back leaves the review watched and stopped with one interrupt. Close wins over a review still being accepted (EC-79).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1 D-23 and 9.2); docs/spec/codex-host-hardening/spec.md (sections 6.1 INV-30 and INV-38, 8.1 D-14 and D-18, and 8.5)
TESTS: tests/features/codex_host/test_codex_host_review_goals.py, tests/features/codex_host/test_codex_host_review_gaps.py, tests/features/codex_host/test_codex_host_fork_review.py, tests/features/codex_host/test_codex_host_failures.py
"""

from __future__ import annotations

from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.lib.constants.codex import CODEX_REVIEW_START_METHOD
from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest, CodexTurnHandle
from vidbyte.lib.dataclasses.codex_host_inputs import CodexReviewRequest
from vidbyte.lib.enums.codex import CodexHostOperation, CodexTurnStatus
from vidbyte.lib.errors import CodexAgentError

if TYPE_CHECKING:
    from openai_codex.generated.v2_all import ReviewStartResponse

    from vidbyte.harnesses.native.codex.connection import CodexConnection
    from vidbyte.harnesses.native.codex.preflight import CodexPreflight
    from vidbyte.harnesses.native.codex.thread_helpers import CodexThreadHelpers
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


class CodexReviews:
    """Starts Codex reviews for one CodexHost, owns each review turn, and reads it back before returning."""

    def __init__(
        self,
        connection: CodexConnection,
        params: CodexParamsTranslator,
        responses: CodexResponseTranslator,
        preflight: CodexPreflight,
        registry: CodexTurnRegistry,
        threads: CodexThreadHelpers,
        events: CodexTurnEvents,
    ) -> None:
        # The host's own parts, built once the host opened.
        self._connection = connection
        self._params = params
        self._responses = responses
        self._preflight = preflight
        self._registry = registry
        self._threads = threads
        self._events = events

    async def start(self, operation: CodexHostOperation, review: CodexReviewRequest) -> CodexTurnHandle:
        # @intent a-review-is-sent-once-and-owned
        # Start a Codex review of a thread's work. review/start spends,
        # so it is sent once, and its turn is owned even when its caller
        # left. Refuse a thread this host is running or starting a turn
        # on, and hold it while the review starts.
        thread_id = review.thread_id
        self._preflight.require_idle(operation, thread_id)
        self._registry.reserve(thread_id)
        try:
            # Check the account, usage and sandbox; a review names no
            # model, and its request carries only Vidbyte's caps.
            await self._preflight.run(operation, review.request, check_model=False)
            thread = await self._preflight.require_thread(operation, thread_id)
            pricing = self._responses.pricing(thread.model or "", thread.model_provider, turn_model="")
            # One review/start; a start that outlives its caller is
            # adopted when Codex accepts it.
            connection = self._connection
            review_call = connection.raw(CODEX_REVIEW_START_METHOD, self._params.review(thread_id, review.target, review.delivery))
            adopt = partial(self._adopt_late, operation, review.request, pricing)
            response = await connection.start(operation, CODEX_REVIEW_START_METHOD, review_call, adopt, thread_id=thread_id)
        finally:
            self._registry.release(thread_id)
        # Register the review turn under its caps, then read it back
        # before returning (hardening INV-30).
        turn = self._track(response, review.request, pricing)
        return await self._accept(operation, turn, late=False)

    def _adopt_late(self, operation: CodexHostOperation, request: CodexSpawnRequest, pricing: CodexAgentSettings, response: ReviewStartResponse) -> None:
        # @intent a-late-review-is-owned-then-stopped
        # Runs on the loop when review/start returns after its caller
        # left. The review is registered at once, then read back like
        # any other and stopped with one interrupt.
        turn = self._track(response, request, pricing)
        self._connection.spawn_task(self._accept(operation, turn, late=True))

    def _track(self, response: ReviewStartResponse, request: CodexSpawnRequest, pricing: CodexAgentSettings) -> CodexLiveTurn:
        # Register the review turn the moment Codex accepted it, so its
        # events are routed to it from now on (D-23), under the
        # caller's caps (hardening INV-30).
        handle = CodexTurnHandle(thread_id=response.review_thread_id, turn_id=response.turn.id)
        self._connection.client.register_turn_notifications(handle.turn_id)
        return self._registry.track(handle, request, pricing, review=True)

    async def _accept(self, operation: CodexHostOperation, turn: CodexLiveTurn, *, late: bool) -> CodexTurnHandle:
        # @intent read-a-registered-review-back
        # Read the review turn back from one page, because openai-codex
        # drops a review turn's events that arrive before registration
        # (D-23, hardening INV-38). A failed read, or one refused after
        # close began, finds nothing stored.
        connection = self._connection
        client = connection.client
        events = self._events
        handle = turn.handle
        stored = None
        # A caller cancelled during the read-back leaves the review
        # owned: it is watched and stopped with one interrupt (INV-11).
        try:
            with suppress(CodexAgentError):
                stored = await self._threads.review_turn(operation, handle.thread_id, handle.turn_id)
        except BaseException:
            turn.watch(connection, events.on_event, events.on_lost)
            turn.stop(connection, None)
            raise
        # Close wins: the turn ends as exited and nothing more is sent.
        if connection.stopped():
            client.unregister_turn_notifications(handle.turn_id)
            self._registry.finish(turn, self._responses.exited(handle))
            if late:
                return handle
            raise CodexErrorMapper.process_exited(operation, handle.thread_id)
        # A review that already ended is built from what was read back.
        # If that build raises, the review ends FAILED through the same
        # failure path as a turn whose events fail, so no wait hangs
        # and the thread takes the next review (hardening INV-12).
        if stored is not None and stored.status.value != CodexTurnStatus.RUNNING.value:
            client.unregister_turn_notifications(handle.turn_id)
            try:
                self._registry.finish(turn, self._responses.turn_snapshot(turn, stored.items, stored))
            except Exception as exc:
                events.fail(turn, exc)
            return handle
        # Otherwise watch it; a late review also gets its one interrupt.
        turn.watch(connection, events.on_event, events.on_lost)
        if late:
            turn.stop(connection, None)
        return handle


__all__ = ["CodexReviews"]
