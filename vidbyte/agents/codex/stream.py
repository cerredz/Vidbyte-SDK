"""FILE: vidbyte/agents/codex/stream.py

PURPOSE: Consumes one native turn stream with deterministic awaited observations.
ROLE IN CODEBASE: CodexTransport delegates opted-in native turns here.
ARCHITECTURE NOTE: Uses public native models, never the private SDK collector.
FUNCTION INVENTORY: run owns cleanup; collect selects result data; deliver awaits observers.
WHAT NOT TO DO: Consume the stream twice or claim callbacks pause the native loop.
KNOWN EDGE CASES: Interrupted turns can lack text; failed/missing terminal events fail.
TESTS: tests/codex_observation/test_observation.py

COMMON MODIFICATION PATTERNS: Extend the native event contract with a matching acceptance case.
RELATED DOCS: docs/design/codex-live-observation.md
"""

from __future__ import annotations

import copy
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Protocol, cast

from vidbyte.agents.codex.observation import CodexEventTranslator, CodexTraceBridge
from vidbyte.agents.codex.result import CodexResultSerializer
from vidbyte.lib.constants.codex import CODEX_EVENT_SEQUENCE_STEP
from vidbyte.lib.dataclasses.codex import (
    CodexObservation,
    CodexRunResult,
    CodexTransportRunRequest,
)

if TYPE_CHECKING:
    from openai_codex import AsyncTurnHandle, TurnResult
    from openai_codex.generated.v2_all import ThreadItem
    from openai_codex.models import Notification

    from vidbyte.agents.codex.transport import _CodexThread


class CodexTurnStream(Protocol):
    """Public stream contract shared by high-level and low-level SDK handles."""

    def stream(self) -> AsyncGenerator[Notification, None]: ...


class CodexStreamRunner:
    """Owns one native stream; each observer receives an isolated reviewed snapshot."""

    def __init__(self, request: CodexTransportRunRequest) -> None:
        # @intent isolated-observation-run
        # Observers and traces belong to one invocation, never shared run state.
        self.settings = request.observation
        self.trace = CodexTraceBridge(self.settings)

    async def run(self, thread: _CodexThread, native_input: Any, *, kwargs: dict[str, Any]) -> CodexRunResult:
        # @intent single-native-stream
        # Cleanup must cover observer failures and cancellation, not only native completion.
        turn = await thread.turn(native_input, **kwargs)
        identity = CodexObservation(0, "", thread.id, turn.id)
        self.trace.start(identity)
        error: BaseException | None = None
        try:
            return CodexResultSerializer.from_sdk(thread.id, await self.collect(turn, identity))
        except BaseException as exc:
            error = exc
            raise
        finally:
            self.trace.finish(error)

    async def collect(self, turn: CodexTurnStream | AsyncTurnHandle, identity: CodexObservation) -> TurnResult:
        # @intent preserve-native-result-semantics
        # Match public result fields while treating absent terminal data as failure.
        from openai_codex import TurnResult
        from openai_codex.generated.v2_all import (
            ItemCompletedNotification,
            ThreadTokenUsageUpdatedNotification,
            TurnCompletedNotification,
        )

        items = []
        usage = None
        completed = None
        sequence = 0
        stream = cast("AsyncGenerator[Notification, None]", turn.stream())
        try:
            async for event in stream:
                sequence += CODEX_EVENT_SEQUENCE_STEP
                await self.deliver(event, CodexObservation(sequence, "", identity.thread_id, identity.turn_id))
                payload = event.payload
                if isinstance(payload, ItemCompletedNotification):
                    items.append(payload.item)
                elif isinstance(payload, ThreadTokenUsageUpdatedNotification):
                    usage = payload.token_usage
                elif isinstance(payload, TurnCompletedNotification):
                    completed = payload.turn
        finally:
            await stream.aclose()
        if completed is None or completed.status.value not in {"completed", "interrupted"}:
            raise ValueError("Codex stream ended without a successful or interrupted terminal event.")
        return TurnResult(id=completed.id, status=completed.status, error=completed.error, started_at=completed.started_at, completed_at=completed.completed_at, duration_ms=completed.duration_ms, final_response=self.final_response(items), items=items, usage=usage)

    async def deliver(self, event: Notification, identity: CodexObservation) -> None:
        # @intent observer-failure-is-not-success
        # Await every observer before advancing; isolate mutable nested item fields.
        observation = CodexEventTranslator.translate(event, identity)
        self.trace.observe(observation)
        for observer in self.settings.observers:
            await observer(copy.deepcopy(observation))

    @staticmethod
    def final_response(items: list[ThreadItem]) -> str | None:
        # @intent preserve-final-answer-phase
        # Prefer an explicit final answer over later commentary or unclassified text.
        from openai_codex.generated.v2_all import AgentMessageThreadItem, MessagePhase

        fallback = None
        for item in reversed(items):
            message = item.root
            if isinstance(message, AgentMessageThreadItem):
                if message.phase == MessagePhase.final_answer:
                    return message.text
                if message.phase is None and fallback is None:
                    fallback = message.text
        return fallback


__all__ = ["CodexStreamRunner"]
