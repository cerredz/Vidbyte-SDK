"""FILE: vidbyte/agents/jev/brief/events.py

PURPOSE: Gives the run brief a numbered view of the main agent's run: the full text of every event by id, which verification checks quotes against, and a bounded window of the events after a given id, which the writer reads.
ROLE IN CODEBASE: JevRunBriefKeeper builds one view per refresh attempt; JevRunBriefWriter reads its window, and JevRunBriefVerifier asks it whether an event contains a quote.
ARCHITECTURE NOTE: Event ids come from JevRunEventLog, so the brief cites the same E-numbered events as REQUIRED_SEQUENCE evidence. This view only reads the log's lines and never renumbers them, and it keeps the full text even when a window shows an event shortened.
COMMON MODIFICATION PATTERNS: Tune window sizes through the JEV_RUN_BRIEF_* character constants; change how events are numbered in JevRunEventLog, not here.
KNOWN EDGE CASES: E1 is the user's request: it is never part of a window, but a quote may cite it. Main-loop tool calls carry their iteration, so ids already assigned do not shift as the run grows. A window always shows at least the newest event's header, even when that header alone exceeds the budget.
RELATED DOCS: docs/design/jev-run-brief.md.
TESTS: tests/test_jev_run_brief.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.lib.constants.jev import (
    JEV_EVENT_ID_PREFIX,
    JEV_RUN_BRIEF_EVENT_HEADER_CHARS,
    JEV_RUN_BRIEF_EVENT_MAX_CHARS,
    JEV_RUN_BRIEF_WINDOW_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import JevRunBriefWindow
from vidbyte.lib.dataclasses.tools import ToolCallContext


class JevRunBriefEvents:
    """The main agent's run as numbered events: full text by id for verification, and bounded windows for the writer."""

    def __init__(self, events: Sequence[tuple[int, str]]) -> None:
        # Keeps each event's number and full text in run order, plus a whitespace-normalized copy for quote lookups.
        self._events = tuple(events)
        self._text = dict(self._events)
        self._normalized = {number: self.normalize(text) for number, text in self._events}

    @classmethod
    def from_run(cls, request: str, responses: Sequence[str], calls: Sequence[ToolCallContext]) -> JevRunBriefEvents:
        """Number the request, the main agent's responses, and its tool calls exactly as JevRunEventLog does."""
        log = JevRunEventLog.from_run(request, responses, calls)
        return cls(tuple(cls._split(line) for line in log.lines))

    @property
    def last_event(self) -> int:
        """Return the number of the newest event, or 0 when the run has none."""
        return self._events[-1][0] if self._events else 0

    def text(self, event: str) -> str | None:
        """Return the full text of one event by its id, such as E14, or None when the run has no such event."""
        number = self._number(event)
        return None if number is None else self._text.get(number)

    def contains(self, event: str, quote: str) -> bool:
        """Return whether the event with this id contains the quote, ignoring differences in whitespace only."""
        # @intent quotes-are-checked-against-the-full-event
        # A window may show an event shortened, but the quote is checked against the event as it happened, so a
        # verbatim passage counts whether or not the writer saw it whole, and nothing outside the event does.
        number = self._number(event)
        needle = self.normalize(quote)
        return number is not None and bool(needle) and needle in self._normalized.get(number, "")

    def window(self, *, after: int) -> JevRunBriefWindow | None:
        """Return the events numbered after `after`, newest kept whole first, or None when there are none."""
        fresh = tuple((number, text) for number, text in self._events if number > after)
        if not fresh:
            return None
        shown = self._fit(fresh)
        omitted = len(fresh) - len(shown)
        lines = [self._omitted_note(omitted)] if omitted else []
        lines.extend(shown)
        return JevRunBriefWindow(first_event=fresh[0][0], last_event=fresh[-1][0], text="\n".join(lines), omitted=omitted)

    @staticmethod
    def clip(text: str, limit: int) -> str:
        """Return the text unchanged when it fits, otherwise its head and tail around a marker that counts what was cut."""
        if len(text) <= limit:
            return text
        head = limit * 2 // 3
        tail = limit - head
        return f"{text[:head]} [... {len(text) - limit} characters left out ...] {text[-tail:]}"

    @staticmethod
    def normalize(text: str) -> str:
        """Collapse every run of whitespace to one space, so line wrapping never decides whether a quote matches."""
        return " ".join(text.split())

    @classmethod
    def _fit(cls, events: tuple[tuple[int, str], ...]) -> tuple[str, ...]:
        # Walks from the newest event back, rendering clipped whole events while they fit, then first-line headers, then stops.
        # @intent the-newest-events-stay-whole
        # The writer already holds the previous brief for everything older, so when space runs out the newest
        # events keep their detail and the oldest new ones shrink first, then drop out and are only counted.
        # The budget covers each line's id prefix and newline and keeps room for the omitted note, so the whole
        # rendered window stays within JEV_RUN_BRIEF_WINDOW_MAX_CHARS.
        budget = JEV_RUN_BRIEF_WINDOW_MAX_CHARS - len(cls._omitted_note(len(events))) - 1
        shown: list[str] = []
        headers_only = False
        for number, text in reversed(events):
            line = cls._line(number, cls._header(text) if headers_only else cls.clip(text, JEV_RUN_BRIEF_EVENT_MAX_CHARS))
            if not headers_only and len(line) + 1 > budget:
                headers_only = True
                line = cls._line(number, cls._header(text))
            if len(line) + 1 > budget and shown:
                break
            shown.append(line)
            budget -= len(line) + 1
        return tuple(reversed(shown))

    @staticmethod
    def _line(number: int, text: str) -> str:
        # Renders one event as the writer reads it, prefixed with its id.
        return f"{JEV_EVENT_ID_PREFIX}{number} {text}"

    @staticmethod
    def _omitted_note(count: int) -> str:
        # Tells the writer how many of the oldest new events did not fit, so it knows the window is incomplete.
        return f"[{count} earlier new events were left out for length]"

    @staticmethod
    def _header(text: str) -> str:
        # Returns the event's first line, bounded, which names the event's kind, tool, and arguments.
        first_line = text.split("\n", 1)[0]
        return f"{first_line[:JEV_RUN_BRIEF_EVENT_HEADER_CHARS]} [... rest of this event left out for length ...]"

    @staticmethod
    def _split(line: str) -> tuple[int, str]:
        # Separates the E-number JevRunEventLog prefixes to every line from the event's text.
        identifier, _, text = line.partition(" ")
        return int(identifier.removeprefix(JEV_EVENT_ID_PREFIX)), text

    @staticmethod
    def _number(event: str) -> int | None:
        # Parses an id such as E14 into 14, or returns None for anything that is not an event id.
        digits = event.removeprefix(JEV_EVENT_ID_PREFIX)
        return int(digits) if event.startswith(JEV_EVENT_ID_PREFIX) and digits.isdigit() else None


__all__ = ["JevRunBriefEvents"]
