"""FILE: vidbyte/agents/jev/done/event_log.py

PURPOSE: Number the request, assistant responses, and tool calls so a required-sequence handoff can cite evidence in run order.
ROLE IN CODEBASE: JevRunState builds this log before each handoff compile and passes its event ids to JevHandoff for citation validation.
ARCHITECTURE NOTE: Event ids are assigned in code from recorded run events; the handoff cannot introduce ids or establish their order.
COMMON MODIFICATION PATTERNS: Change which recorded events appear in from_run() and keep event_ids() aligned with the displayed log.
KNOWN EDGE CASES: The user's request is context only and is excluded from citable ids; isDone calls are control flow, not evidence.
RELATED DOCS: docs/design/jev-claims-context.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_required_sequence.py and tests/test_jev_done.py.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence

from vidbyte.lib.constants.jev import (
    JEV_EVENT_LOG_FIRST_ID,
    JEV_EVENT_LOG_ID_INCREMENT,
    JEV_EVENT_LOG_INITIAL_ITERATION,
    JEV_EVENT_LOG_ITERATION_OFFSET,
    JEV_EVENT_LOG_NEXT_ID,
)
from vidbyte.lib.dataclasses.jev import JevContinuationEvidence
from vidbyte.lib.dataclasses.tools import ToolCallContext
from vidbyte.tools._internal import IS_DONE_TOOL_NAME


class JevRunEventLog:
    """A stable, ordered view of the request, assistant responses, and tool calls."""

    def __init__(self, lines: Sequence[str]) -> None:
        self.lines = tuple(lines)

    @classmethod
    def from_run(cls, request: str, responses: Sequence[str], calls: Sequence[ToolCallContext]) -> JevRunEventLog:
        """Assign event ids in loop order so stage evidence can cite an exact run event."""
        # @intent event-ids-follow-recorded-run-order
        # The handoff can cite only events in this list, and code compares their ids to check sequence order.
        return cls._from_segments(request, ((None, responses, calls),))

    @classmethod
    def from_segments(cls, request: str, segments: Sequence[JevContinuationEvidence]) -> JevRunEventLog:
        """Assign global event ids while retaining each continuation segment's local chronology and source."""
        # @intent continuation-segments-share-citable-global-order
        # Required-sequence evidence cites one finish-attempt event set, even when a clean-context attempt restarts local iterations.
        # Keep segment order and source labels so repeated local iteration numbers cannot make later evidence appear earlier.
        return cls._from_segments(
            request,
            ((segment.source, segment.responses, segment.tool_calls) for segment in segments),
        )

    @classmethod
    def _from_segments(
        cls,
        request: str,
        segments: Iterable[tuple[str | None, Sequence[str], Sequence[ToolCallContext]]],
    ) -> JevRunEventLog:
        """Render ordered local traces under one request event and a single global id counter."""
        # @intent request-is-noncitable-and-events-are-contiguous
        # The request frames the log but cannot prove work; every response or tool call gets the next event id across segments.
        # A missing or restarted local iteration must not duplicate IDs or weaken deterministic sequence validation.
        lines = [f"E{JEV_EVENT_LOG_FIRST_ID} USER: {request}"]
        number = JEV_EVENT_LOG_NEXT_ID
        for source, responses, calls in segments:
            number = cls._append_segment(lines, source, responses, calls, number)
        return cls(lines)

    @staticmethod
    def _append_segment(
        lines: list[str],
        source: str | None,
        responses: Sequence[str],
        calls: Sequence[ToolCallContext],
        first_number: int,
    ) -> int:
        """Append one segment's events and return the next available global id."""
        by_iteration: dict[int, list[ToolCallContext]] = defaultdict(list)
        for call in calls:
            if call.tool_name == IS_DONE_TOOL_NAME:
                continue
            by_iteration[call.iteration_count or JEV_EVENT_LOG_INITIAL_ITERATION].append(call)
        number = first_number
        label = "" if source is None else f"source={source} "
        for call in by_iteration.get(JEV_EVENT_LOG_INITIAL_ITERATION, ()):
            state = call.result.status.value if call.result is not None else call.state.value
            arguments = json.dumps(dict(call.arguments), default=str, sort_keys=True)
            lines.append(f"E{number} {label}TOOL {call.tool_name} state={state}: arguments={arguments} output={call.output or ''}")
            number += JEV_EVENT_LOG_ID_INCREMENT
        for iteration in range(max(len(responses), max(by_iteration, default=JEV_EVENT_LOG_INITIAL_ITERATION)) + JEV_EVENT_LOG_ITERATION_OFFSET):
            if iteration < len(responses) and responses[iteration].strip():
                lines.append(f"E{number} {label}ASSISTANT iteration={iteration + JEV_EVENT_LOG_ITERATION_OFFSET}: {responses[iteration]}")
                number += JEV_EVENT_LOG_ID_INCREMENT
            for call in by_iteration.get(iteration + JEV_EVENT_LOG_ITERATION_OFFSET, ()):
                state = call.result.status.value if call.result is not None else call.state.value
                arguments = json.dumps(dict(call.arguments), default=str, sort_keys=True)
                lines.append(f"E{number} {label}TOOL {call.tool_name} state={state}: arguments={arguments} output={call.output or ''}")
                number += JEV_EVENT_LOG_ID_INCREMENT
        return number

    def event_ids(self) -> frozenset[str]:
        """Return the identifiers the handoff may cite."""
        return frozenset(
            identifier
            for line in self.lines
            for identifier, separator, event in (line.partition(" "),)
            if separator and not event.startswith("USER: ")
        )

    def render(self) -> str:
        """Return the numbered log for the handoff builder."""
        return "\n".join(self.lines)


__all__ = ["JevRunEventLog"]
