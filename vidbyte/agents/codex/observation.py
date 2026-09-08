"""FILE: vidbyte/agents/codex/observation.py

PURPOSE: Converts reviewed native events into safe observations and tool spans.
ROLE IN CODEBASE: CodexStreamRunner delivers these records to caller observers.
ARCHITECTURE NOTE: Native models are loaded lazily; tracing receives identity only.
FUNCTION INVENTORY: translate validates identity; start/observe/finish own spans.
WHAT NOT TO DO: Export arbitrary native payloads or infer hidden model calls.
KNOWN EDGE CASES: Unknown events carry no payload; duplicate starts are ignored.
TESTS: tests/codex_observation/test_observation.py

COMMON MODIFICATION PATTERNS: Extend the native event contract with a matching acceptance case.
RELATED DOCS: docs/design/codex-live-observation.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.agents.codex.result import CodexResultSerializer
from vidbyte.lib.dataclasses.codex import CodexObservation, CodexObservationSettings
from vidbyte.lib.enums.codex import CodexEventMethod
from vidbyte.lib.tracing import SpanContext

if TYPE_CHECKING:
    from openai_codex.models import Notification


class CodexEventTranslator:
    """Copies only reviewed native item payloads after identity validation."""

    @staticmethod
    def translate(event: Notification, identity: CodexObservation) -> CodexObservation:
        # @intent exclude-private-reasoning
        # Reject cross-run data and exclude private content before any callback sees it.
        from openai_codex.generated.v2_all import (
            ItemCompletedNotification,
            ItemStartedNotification,
            ThreadTokenUsageUpdatedNotification,
            TurnCompletedNotification,
        )

        payload = event.payload
        item = None
        if isinstance(payload, (ItemStartedNotification, ItemCompletedNotification, ThreadTokenUsageUpdatedNotification)):
            if payload.thread_id != identity.thread_id or payload.turn_id != identity.turn_id:
                raise ValueError("Codex observation identity does not match the active turn.")
        if isinstance(payload, TurnCompletedNotification):
            if payload.thread_id != identity.thread_id or payload.turn.id != identity.turn_id:
                raise ValueError("Codex completion identity does not match the active turn.")
        if isinstance(payload, (ItemStartedNotification, ItemCompletedNotification)):
            item = CodexResultSerializer._item(payload.item)
        return CodexObservation(identity.sequence, event.method, identity.thread_id, identity.turn_id, item)


class CodexTraceBridge:
    """Best-effort trace lifecycle with no raw provider payloads or exception text."""

    def __init__(self, settings: CodexObservationSettings) -> None:
        # Retain the caller tracer and allocate isolated span state for one turn.
        self.tracer = settings.tracer
        self.root: SpanContext | None = None
        self.spans: dict[str, SpanContext] = {}
        self.error_count = 0

    def start(self, identity: CodexObservation) -> None:
        # @intent tracing-cannot-abort-execution
        # Provider failures remain optional instrumentation failures.
        try:
            self.root = self.tracer.start_trace("agent.run", thread_id=identity.thread_id, turn_id=identity.turn_id)
        except Exception:
            self.error_count += 1

    def observe(self, observation: CodexObservation) -> None:
        # Record native lifecycle boundaries without manufacturing missing starts.
        item = observation.item
        if item is None or self.root is None:
            return
        try:
            if observation.method == CodexEventMethod.ITEM_STARTED and item.id not in self.spans:
                if item.type in {"commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall", "webSearch"}:
                    self.spans[item.id] = self.tracer.start_span("tool.call", parent=self.root, item_id=item.id, tool_name=item.type)
            elif observation.method == CodexEventMethod.ITEM_COMPLETED and item.id in self.spans:
                self.tracer.end_span(self.spans.pop(item.id))
        except Exception:
            self.error_count += 1

    def finish(self, error: BaseException | None) -> None:
        # Close outstanding children before the root without exporting raw failures.
        safe_error = RuntimeError(type(error).__name__) if error is not None else None
        for span in reversed(tuple(self.spans.values())):
            try:
                self.tracer.end_span(span, error=safe_error)
            except Exception:
                self.error_count += 1
        self.spans.clear()
        if self.root is not None:
            try:
                self.tracer.end_trace(self.root, error=safe_error)
            except Exception:
                self.error_count += 1
            self.root = None


__all__ = ["CodexEventTranslator", "CodexTraceBridge"]
