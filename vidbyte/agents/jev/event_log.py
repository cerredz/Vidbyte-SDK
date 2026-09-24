"""FILE: vidbyte/agents/jev/event_log.py

PURPOSE: Builds the numbered event log the handoff builder reads, directly from the runtime loop state at a finish attempt.
ROLE IN CODEBASE: JevRuntime.review_finish_attempt calls JevRunEventLog.from_loop_state and passes the rendered log to JevRunHandoffAgent; section parsers check cited event IDs against it.
ARCHITECTURE NOTE: No middleware records anything; the loop state already holds the request, each iteration's assistant text, and every tool call tagged with its iteration, and those lists only grow, so IDs stay stable across finish attempts.
COMMON MODIFICATION PATTERNS: Add a new event source by appending events in iteration order inside from_loop_state; never reorder existing sources, because earlier handoffs cite their IDs.
KNOWN EDGE CASES: isDone calls are skipped because the proposed answer is passed separately; only the final attempt of a retried tool call exists in call_contexts; long bodies are cut with an explicit marker, never silently.
RELATED DOCS: docs/design/jev-required-sequence.md.
TESTS: tests/test_jev_required_sequence.py.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence

from vidbyte.agents.jev.run_state import JevRunEvent
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.constants.jev import JEV_EVENT_ID_PREFIX, JEV_EVENT_LOG_MAX_EVENT_CHARS
from vidbyte.lib.enums.jev_run_state import JevRunEventKind
from vidbyte.tools._internal import IS_DONE_TOOL_NAME
from vidbyte.tools.types import ToolCallContext

_FIRST_ITERATION = 1
_BEFORE_FIRST_ITERATION = 0


class JevRunEventLog:
    """Ordered, numbered events of one run as seen at a finish attempt."""

    def __init__(self, events: Sequence[JevRunEvent]) -> None:
        # Retains the events exactly as numbered by from_loop_state.
        self.events: tuple[JevRunEvent, ...] = tuple(events)

    @classmethod
    def from_loop_state(cls, state: BaseAgentRuntimeLoopState, *, review_feedback: Sequence[tuple[int, str]] = ()) -> JevRunEventLog:
        """Number the request, each iteration's assistant text and tool calls, and earlier review feedback."""
        # @intent event-ids-are-append-only
        # Events are emitted strictly by iteration and, within one, text -> tools -> feedback, and every
        # source list only grows; a rebuilt log therefore keeps every ID an earlier handoff cited.
        calls: dict[int, list[ToolCallContext]] = defaultdict(list)
        for context in state.call_contexts:
            if context.tool_name != IS_DONE_TOOL_NAME:
                calls[context.iteration_count or _BEFORE_FIRST_ITERATION].append(context)
        feedback: dict[int, list[str]] = defaultdict(list)
        for iteration, text in review_feedback:
            feedback[iteration].append(text)
        builder = _EventNumbering()
        builder.add(JevRunEventKind.USER, _BEFORE_FIRST_ITERATION, "user", state.message)
        builder.add_tools(_BEFORE_FIRST_ITERATION, calls.get(_BEFORE_FIRST_ITERATION, ()))
        for iteration, output in enumerate(state.iteration_outputs, start=_FIRST_ITERATION):
            if output.strip():
                builder.add(JevRunEventKind.ASSISTANT, iteration, "assistant", output)
            builder.add_tools(iteration, calls.get(iteration, ()))
            for text in feedback.get(iteration, ()):
                builder.add(JevRunEventKind.FINISH_REVIEW, iteration, "finish review", text)
        return cls(builder.events)

    def event_ids(self) -> frozenset[str]:
        """Return every event ID a handoff may cite."""
        return frozenset(event.event_id for event in self.events)

    def last_event_id(self) -> str:
        """Return the ID of the newest event, which bounds what a handoff describes."""
        return self.events[-1].event_id

    def render(self) -> str:
        """Render one line per event for the handoff builder."""
        return "\n".join(event.render() for event in self.events)


class _EventNumbering:
    """Assigns consecutive event IDs while the log is being assembled."""

    def __init__(self) -> None:
        # Starts numbering at E1 with an empty event list.
        self.events: list[JevRunEvent] = []

    def add(self, kind: JevRunEventKind, iteration: int, label: str, text: str) -> None:
        # Appends one event with the next ID and a length-bounded body.
        event_id = f"{JEV_EVENT_ID_PREFIX}{len(self.events) + 1}"
        self.events.append(JevRunEvent(event_id=event_id, kind=kind, iteration=iteration, label=label, text=_clip(text)))

    def add_tools(self, iteration: int, contexts: Sequence[ToolCallContext]) -> None:
        # Appends each tool call with its arguments, final status, and output.
        for context in contexts:
            status = context.result.status.value if context.result is not None else context.state.value
            arguments = json.dumps(dict(context.arguments), default=str, sort_keys=True)
            self.add(JevRunEventKind.TOOL, iteration, f"tool {context.tool_name}, {status}", f"arguments={arguments} output={context.output or ''}")


def _clip(text: str) -> str:
    # Cuts an oversized body and says how much is hidden, so the builder can report the limitation.
    if len(text) <= JEV_EVENT_LOG_MAX_EVENT_CHARS:
        return text
    hidden = len(text) - JEV_EVENT_LOG_MAX_EVENT_CHARS
    return f"{text[:JEV_EVENT_LOG_MAX_EVENT_CHARS]} [... {hidden} more characters not shown]"


__all__ = ["JevRunEventLog"]
